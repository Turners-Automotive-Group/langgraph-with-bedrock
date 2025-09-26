import os

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
    try:
        print(f"Getting memory for namespace: {namespace}")

        # Let's try to query the raw data first to see what's actually stored
        import psycopg
        DB_URI = f"postgresql://{os.getenv('DB_USERNAME')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:5432/{os.getenv('DB_NAME')}"
        with psycopg.connect(DB_URI) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT value FROM store WHERE prefix = %s AND key = %s",
                           (f"{namespace[0]}.{namespace[1]}", "special_instructions"))
                raw_row = cur.fetchone()


        # Search for existing memory with namespace and key
        special_instructions = store.get(namespace, "special_instructions")

        # If memory exists, return its content (the value)
        if special_instructions:
            # Handle both old format (direct string) and new format (dict with 'value' key)
            if isinstance(special_instructions.value, dict) and 'value' in special_instructions.value:
                return special_instructions.value['value']
            else:
                return special_instructions.value

        # Return the default content
        print(f"Returning default: {default_content}")
        return default_content
    except Exception as e:
        print(f"Error in get_memory: {e}")
        import traceback
        traceback.print_exc()
        raise

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
    try:
        result: UserPreferences | dict = memory_llm.invoke(
        [
            {"role": "system",
             "content": MEMORY_UPDATE_INSTRUCTIONS.format(current_profile=instructions_value, namespace=namespace)},
        ] + messages
        )
    except Exception as e:
        print(f"Error invoking memory_llm: {e}")
        print(f"Messages: {messages}")
        raise

    # Save the updated memory to the store
    # The PostgreSQL store expects JSON values, so we need to store the string as JSON
    print(f"Storing memory: {result.special_instructions}")
    store.put(namespace, "special_instructions", {"value": result.special_instructions})