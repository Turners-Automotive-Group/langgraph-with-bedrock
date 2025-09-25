from langchain.chat_models import init_chat_model
from langchain_aws import ChatBedrock
from pydantic import BaseModel, Field

from prompts import MEMORY_UPDATE_INSTRUCTIONS


class UserPreferences(BaseModel):
    """Updated user preferences based on user's feedback."""
    chain_of_thought: str = Field(description="Reasoning about which special instructions need to add / update if required")
    special_instructions: str = Field(description="Updated special instructions")


llm = ChatBedrock(
        model="amazon.nova-lite-v1:0",
        model_kwargs={"temperature": 0}
    )
memory_llm = llm.with_structured_output(UserPreferences)


def get_memory(store, namespace, default_content=None):
    """Get memory from the store or initialize with default if it doesn't exist.

    Args:
        store: LangGraph BaseStore instance to search for existing memory
        namespace: Tuple defining the memory namespace, e.g. ("email_assistant", "triage_preferences")
        default_content: Default content to use if memory doesn't exist

    Returns:
        str: The content of the memory profile, either from existing memory or the default
    """
    # Search for existing memory with namespace and key
    special_instructions = store.get(namespace, "special_instructions")

    # If memory exists, return its content (the value)
    if special_instructions:
        return special_instructions.value

    # Return the default content
    return default_content

def update_memory(store, namespace, messages):
    """Update memory profile in the store.

    Args:
        store: LangGraph BaseStore instance to update memory
        namespace: Tuple defining the memory namespace, e.g. ("email_assistant", "triage_preferences")
        messages: List of messages to update the memory with
    """

    # Get the existing memory
    special_instructions = store.get(namespace, "special_instructions")
    if special_instructions:
        instructions_value = special_instructions.value
    else:
        instructions_value = 'No special instructions'
    # Update the memory
    result: UserPreferences | dict = memory_llm.invoke(
    [
        {"role": "system",
         "content": MEMORY_UPDATE_INSTRUCTIONS.format(current_profile=instructions_value, namespace=namespace)},
    ] + messages
    )

    # Save the updated memory to the store
    store.put(namespace, "special_instructions", result.special_instructions)