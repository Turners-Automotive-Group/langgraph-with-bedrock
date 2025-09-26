import logging
import os

from langchain_core.runnables import RunnableConfig

from agent_memory import get_memory, update_memory
from agent_state import State
from db_utils import table_exists
from prompts import agent_system_prompt_hitl_memory, HITL_MEMORY_TOOLS_PROMPT, MEMORY_UPDATE_INSTRUCTIONS_REINFORCEMENT

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
from typing import Literal

from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langchain_aws import ChatBedrock
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.store.postgres import PostgresStore

from langgraph.constants import END, START
from langgraph.graph import StateGraph
from langgraph.prebuilt import ToolNode
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from pydantic import BaseModel, Field
from langgraph.types import interrupt, Command
from langgraph.store.base import BaseStore

log = logging.getLogger(__name__)

app = BedrockAgentCoreApp()

class Excursion(BaseModel):
    name: str = Field(description="The name of the excursion")
    ideal_in_weather: list[str] = Field(description="List to weather conditions ideal for this excursion")

DB_URI = f"postgresql://{os.getenv('DB_USERNAME')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:5432/{os.getenv('DB_NAME')}"

# Check if tables exist before running setup
checkpoints_exist = table_exists(DB_URI, "checkpoints")
store_exists = table_exists(DB_URI, "store")

# Create direct connection objects (not context managers)
from psycopg_pool import ConnectionPool

# Setup function for initializing tables
def setup_tables_if_needed():
    if not store_exists:
        log.info("Store table does not exist, running store.setup()")
        with PostgresStore.from_conn_string(DB_URI) as store_temp:
            store_temp.setup()

    if not checkpoints_exist:
        log.info("Checkpoints table does not exist, running checkpointer.setup()")
        with PostgresSaver.from_conn_string(DB_URI) as checkpointer_temp:
            checkpointer_temp.setup()

# Run table setup
setup_tables_if_needed()

# Create persistent connections by directly instantiating with connection pool
conn_pool = ConnectionPool(DB_URI, min_size=1, max_size=10)
store = PostgresStore(conn=conn_pool)
checkpointer = PostgresSaver(conn=conn_pool)

@tool
def available_excursions() -> list[Excursion]:
    """
    Returns a list of available excursions.

    Returns:
        str: A list of available excursions.
    """
    return [
        Excursion(name="Sailing", ideal_in_weather=["windy", "sunny"]),
        Excursion(name="Diving", ideal_in_weather=["sunny"]),
        Excursion(name="Dota", ideal_in_weather=["rainy", "windy", "sunny"]),
    ]


@tool
def weather():
    """Get weather"""
    return "sunny"

@tool()
def book_excursion(excursion: Excursion) -> bool:
    """
    Book an excursion
    Args:
        excursion: the excursion to book

    Returns:
        bool: True if the excursion was booked

    """
    return True

@tool
class Done(BaseModel):
      """Task Complete."""
      done: bool


def create_agent():
    """Create agent"""

    llm = ChatBedrock(
        model="amazon.nova-lite-v1:0",
        model_kwargs={"temperature": 0}
    )

    tools = [available_excursions, weather, book_excursion, Done]
    llm_with_tools = llm.bind_tools(tools)


    def load_user(state: State, config: RunnableConfig):
        user_id = config.get("configurable", {}).get("user_id")
        return {
            'user_id': user_id
        }

    def chatbot(state: State, store: BaseStore):
        """LLM decides whether to call a tool or not"""

        log.info("in here chatbot")
        # Search for existing cal_preferences memory
        special_instructions = get_memory(store, (state['user_id'], "special_instructions"), "No Special Instructions yet")
        log.info(f"special_instructions: {special_instructions}")
        background = get_memory(store, (state['user_id'], "background"), "No Background yet")
        log.info(f"background: {background}")

        return {
            "messages": [
                llm_with_tools.invoke(
                    [
                        {"role": "system",
                         "content": agent_system_prompt_hitl_memory.format(tools_prompt=HITL_MEMORY_TOOLS_PROMPT,
                                                                           background=background,
                                                                           special_instructions=special_instructions,
                                                                           )}
                    ]
                    + state["messages"]
                )
            ]
        }

    def interrupt_handler(state: State) -> Command[Literal["tools", "chatbot", "__end__"]]:
        # Store messages
        update = {
            "messages": [],
        }

        # Go to the LLM call node next
        goto = "tools"

        for tool_call in state["messages"][-1].tool_calls:
            hitl_tools = [book_excursion.name]

            if tool_call["name"] not in hitl_tools:
                # Execute tool without interruption
                goto = "tools"
                continue

            if tool_call["name"] == book_excursion.name:
                config = {
                    "message": "Confirm booking this excursion.",
                    "options": ["confirm", "cancel", "feedback"]
                }
            else:
                raise ValueError(f"Invalid tool call: {tool_call['name']}")

            # Create the interrupt request
            request = {
                "action_request": {
                    "action": tool_call["name"],
                    "args": tool_call["args"]
                },
                "config": config,
            }

            response = interrupt([request])[0]
            log.info('response from interrupt')
            log.info(response)

            if response["option"] == "confirm":
                goto = "tools"
                continue
            elif response["option"] == "cancel":
                # Go to END
                goto = END
                continue
            elif response["option"] == "feedback":
                goto = "chatbot"

                user_feedback = response["args"]["user_feedback"]
                feedback_result = {"role": "tool",
                       "content": f"User gave feedback, which can we incorporate into the meeting request. Feedback: {user_feedback}",
                       "tool_call_id": tool_call["id"]}
                update["messages"].append(feedback_result)
                update_memory(store, (state['user_id'], "special_instructions"),
                              state["messages"] +
                              [feedback_result]
                              )

        # Update the state
        return Command(goto=goto, update=update)

    # Conditional edge function
    def should_continue(state: State) -> Literal["interrupt_handler", "end"]:
        """Route to tool handler, or end if Done tool called"""
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            for tool_call in last_message.tool_calls:
                if tool_call["name"] == "Done":
                    return "end"
                else:
                    return "interrupt_handler"

        return "end"

    # Create the graph
    graph_builder = StateGraph(State)

    # Add nodes
    graph_builder.add_node("load_user", load_user)
    graph_builder.add_node("chatbot", chatbot)
    graph_builder.add_node("interrupt_handler", interrupt_handler)
    graph_builder.add_node("tools", ToolNode(tools))

    # Add edges
    graph_builder.add_edge(START, "load_user")
    graph_builder.add_edge("load_user", "chatbot")
    graph_builder.add_conditional_edges(
        "chatbot",
        should_continue,
        {
            "interrupt_handler": "interrupt_handler",
            "end": END,

        }
    )
    graph_builder.add_edge("tools", "chatbot")


    return graph_builder.compile(checkpointer=checkpointer, store=store)

# Initialize Agent
agent = create_agent()

@app.entrypoint
def langgraph_bedrock(payload):
    """
    Invoke the agent with a payload
    """
    thread_id = payload.get("thread_id")
    user_id = payload.get("user_id")

    user_input = payload.get("prompt")
    user_command = payload.get("command")
    user_feedback = payload.get("feedback")

    if user_command:
        args = {}
        if user_feedback:
            args['user_feedback'] = user_feedback

        response = agent.invoke(
            Command(
                resume=[{"option": user_command, "args": args}]),
                config={
                    "thread_id": thread_id,
                    "user_id": user_id,
                }
        )
    else:
        response = agent.invoke(
            {
                "messages": [HumanMessage(content=user_input)],
            },
            config={
                "thread_id": thread_id,
                "user_id": user_id,
            }
        )

    log.info(response)

    if "__interrupt__" in response:
        return response["__interrupt__"]

    final_content = response["messages"][-1].content
    return final_content

if __name__ == "__main__":
    app.run()