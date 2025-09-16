import argparse
import json
import operator

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.tools import tool
from langchain_aws import ChatBedrock
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from pydantic import BaseModel, Field

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


def create_agent():
    """Create agent"""

    llm = ChatBedrock(
        model="amazon.nova-lite-v1:0",
        model_kwargs={"temperature": 0}
    )

    tools = [available_excursions, weather, book_excursion]
    llm_with_tools = llm.bind_tools(tools)

    system_message = "You are a excursion booking assistant. You can help customers find and book excursions according the the weather and the customers preferences."

    def chatbot(state: MessagesState):
        messages = state["messages"]
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=system_message)] + messages

        response = llm_with_tools.invoke(messages)
        return {"messages": [response]}

    # Create the graph
    graph_builder = StateGraph(MessagesState)

    # Add nodes
    graph_builder.add_node("chatbot", chatbot)
    graph_builder.add_node("tools", ToolNode(tools))

    # Add edges
    graph_builder.add_conditional_edges(
        "chatbot",
        tools_condition,
    )
    graph_builder.add_edge("tools", "chatbot")
    graph_builder.set_entry_point("chatbot")

    checkpointer = MemorySaver()

    return graph_builder.compile(checkpointer=checkpointer)

# Initialize Agent
agent = create_agent()

@app.entrypoint
def langgraph_bedrock(payload):
    """
    Invoke the agent with a payload
    """
    user_input = payload.get("prompt")

    response = agent.invoke(
        {
            "messages": [HumanMessage(content=user_input)],
        },
        config={
            "thread_id": "fc6faede-87f7-4e91-a172-eacd7230d405"
        }
    )

    return response["messages"][-1].content

if __name__ == "__main__":
    app.run()