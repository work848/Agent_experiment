
from src.llm.openai_client_normal import call_gpt
from langchain.agents import AgentState


def chat_node(state: AgentState):

    messages = state.messages

    SYSTEM_PROMPT = """
You are a product manager.

Your job is to:
- Understand the user's requirements
- Ask clarifying questions
- Suggest improvements
- Help refine the idea BEFORE planning

DO NOT generate implementation plans.
DO NOT output JSON.
Just chat naturally.
"""

    response = call_gpt(
        messages=[{"role": "system", "content": SYSTEM_PROMPT}] + messages[-20:],
        tools=None,
        temperature=0.7
    )

    reply = response["choices"][0]["message"]["content"]

    # 写回对话
    return {
        "messages": messages + [{"role": "assistant", "content": reply}]
    }