from llm.openai_client import call_gpt
# from tools.list_files_tool import read_project_files


SYSTEM_PROMPT = """
You are a coding AI assistant.

Follow these rules:
- Never invent files that do not exist
- Use the provided project context
- Pay attention to variable names and functions
"""


def llm_node(state):

    messages = state["messages"]

    # ===== conversation window =====
    conversation = messages[-6:]

    # ===== code context =====
    # code_context = read_project_files()

    code_text = ""


    system_prompt = {
        "role": "system",
        "content": f"""
        {SYSTEM_PROMPT}
        """
            }

    prompt_messages = [
        system_prompt,
        *conversation
    ]

    response = call_gpt(prompt_messages)

    tool_call = bool(response.get("tool_calls", []))
    return {
        "messages": messages + [response],
        "tool_call": tool_call
    }