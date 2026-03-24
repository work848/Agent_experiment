from langgraph.graph import StateGraph, END
from agent.state import AgentState
from agent.state import Mode
from utils.user_action import handle_user_action



def central_coordinator(state: AgentState):
    # 工具调用流程
    if state.tool_call:
        return state.current_agent

    # 邮件调用流程
    for mail in state.mailbox:
        if not mail.is_resolved:
            return mail.target
    if state.success:
        return END


    #用户流程
    if state.last_user_action:
        state = handle_user_action(state.last_user_action, state)
        state.last_user_action = None  # 防止重复触发
        # ✅ 如果 handle_user_action 已经指定 next_node，直接返回
        if state.next_node:
            next_node = state.next_node  # 先存
            state.next_node = None       # 再清
            return next_node.value

    # 正常调度逻辑
    if state.mode == Mode.CHAT:
        # CHAT 模式每次请求只执行一轮：
        # 如果最新一条已经是 assistant 回复，则结束，避免 chat->coordinator 死循环
        if state.messages:
            last_message = state.messages[-1]
            if isinstance(last_message, dict) and last_message.get("role") == "assistant":
                return END
        return "chat"
    if state.mode == Mode.PLANNING:
        if state.trigger_plan:
            print("plan is here")
            return "planner"
        if state.interface_refresh:
            return  "interface"
        if state.current_agent == "planner":
            return "interface"
        if state.current_agent == "interface":
            return END
    if state.mode == Mode.EXECUTING:
            return END

    # if state.current_agent == "coder":
    #     return "executor"

    # if state.current_agent == "executor":
    #     return "tester"

    # if state.current_agent == "tester":
    #     return END
    return END


