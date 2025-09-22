import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
from typing import Literal

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.tools import tool
from langchain_aws import ChatBedrock
from langgraph.checkpoint.memory import MemorySaver
from langgraph.constants import END, START
from langgraph.graph import MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from pydantic import BaseModel, Field
from langgraph.types import interrupt, Command

log = logging.getLogger(__name__)

app = BedrockAgentCoreApp()

class Excursion(BaseModel):
    name: str = Field(description="The name of the excursion")
    ideal_in_weather: list[str] = Field(description="List to weather conditions ideal for this excursion")

@tool
def available_excursions() -> list[Excursion]:
    """
    Returns a list of available excursions.

    Returns:
        str: A list of available excursions.
    """
    return [
        Excursion(name="Sailing", ideal_in_weather=["windy"]),
        Excursion(name="Diving", ideal_in_weather=["sunny"]),
        Excursion(name="Dota", ideal_in_weather=["rainy"]),
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

    system_message = """
    You are a excursion booking assistant. You can help customers find and book excursions according the the weather and the customers preferences.
    1. Use the provided tools to find and book excursions.
    2. IMPORTANT --- always call one tool at a time until the task is complete: 
    3. once the task is finished, use the Done tool to indicate that the task is complete

    """

    def chatbot(state: MessagesState):
        messages = state["messages"]
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=system_message)] + messages

        response = llm_with_tools.invoke(messages)
        return {"messages": [response]}

    def interrupt_handler(state: MessagesState) -> Command[Literal["tools", "__end__"]]:
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
                    "options": ["confirm", "cancel"]
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

        # Update the state
        return Command(goto=goto, update=update)

    # Conditional edge function
    def should_continue(state: MessagesState) -> Literal["interrupt_handler", "end"]:
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
    graph_builder = StateGraph(MessagesState)

    # Add nodes
    graph_builder.add_node("chatbot", chatbot)
    graph_builder.add_node("interrupt_handler", interrupt_handler)
    graph_builder.add_node("tools", ToolNode(tools))

    # Add edges
    graph_builder.add_edge(START, "chatbot")
    graph_builder.add_conditional_edges(
        "chatbot",
        should_continue,
        {
            "interrupt_handler": "interrupt_handler",
            "end": END,

        }
    )
    graph_builder.add_edge("tools", "chatbot")

    checkpointer = MemorySaver()

    return graph_builder.compile(checkpointer=checkpointer)

# Initialize Agent
agent = create_agent()

@app.entrypoint
def langgraph_bedrock(payload):
    """
    Invoke the agent with a payload
    """
    thread_id = payload.get("thread_id")

    user_input = payload.get("prompt")
    user_command = payload.get("command")

    if user_command:
        response = agent.invoke(
            Command(
                resume=[{"option": user_command, "args": {}}]),
                config={
                    "thread_id": thread_id
                }
        )
    else:
        response = agent.invoke(
            {
                "messages": [HumanMessage(content=user_input)],
            },
            config={
                "thread_id": thread_id
            }
        )

    log.info(response)

    if "__interrupt__" in response:
        return response["__interrupt__"]

    return response["messages"][-1].content

if __name__ == "__main__":
    app.run()