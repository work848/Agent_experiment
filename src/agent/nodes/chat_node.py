from src.llm.openai_client_normal import call_gpt
from agent.state import AgentState, Mode, NextNode


CTA_ACTIONS = [
    {"action": "generate_plan", "label": "生成计划"},
    {"action": "continue_chat", "label": "继续补充"},
]


def _is_ready_for_plan(messages):
    last_user = ""
    for m in reversed(messages):
        if isinstance(m, dict) and m.get("role") == "user":
            last_user = str(m.get("content") or "").strip()
            break

    if not last_user:
        return False

    # 简单规则：消息较长或出现目标/实现类关键词时，认为可进入生成计划 CTA
    keywords = ["实现", "开发", "做一个", "build", "create", "feature", "系统", "需求", "功能"]
    if len(last_user) >= 20:
        return True
    return any(k in last_user.lower() for k in keywords)


def chat_node(state: AgentState):

    messages = state.messages
    was_ready_for_plan = bool(state.ready_for_plan)
    ready_for_plan = _is_ready_for_plan(messages)

    # 当上一轮已完成澄清时，本轮自动切到规划（不再追加 chat 回复）
    if state.mode == Mode.CHAT and was_ready_for_plan:
        return {
            "ready_for_plan": True,
            "suggested_actions": CTA_ACTIONS,
            "mode": Mode.PLANNING,
            "trigger_plan": True,
            "next_node": NextNode.PLANNER,
        }

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
DO NOT tell user that I have  I can see you uploaded a file.
"""

    response = call_gpt(
        messages=[{"role": "system", "content": SYSTEM_PROMPT}] + messages[-4:],
        tools=None,
        temperature=0.7
    )

    reply = response["choices"][0]["message"]["content"]

    # 首次达到阈值时只提示，等待下一次请求自动进入规划
    if ready_for_plan and not was_ready_for_plan:
        reply = "需求信息已经足够完整。下一次请求我会自动进入规划并生成计划。"

    updated_messages = messages + [{"role": "assistant", "content": reply}]

    # 写回对话
    return {
        "messages": updated_messages,
        "ready_for_plan": ready_for_plan,
        "suggested_actions": CTA_ACTIONS if ready_for_plan else [],
    }
