from langgraph.graph import END
from agent.state import AgentState, Mode, NextNode, RunStatus
from utils.user_action import handle_user_action


def _node_value(node):
    if isinstance(node, NextNode):
        return node.value
    return node


def central_coordinator(state: AgentState):
    if state.tool_call:
        return _node_value(state.current_agent)

    for mail in state.mailbox:
        if not mail.is_resolved:
            return mail.target

    if state.success:
        return END

    if state.next_node == NextNode.ERROR:
        return NextNode.ERROR.value

    if state.last_user_action:
        state = handle_user_action(state.last_user_action, state)
        state.last_user_action = None
        if state.next_node:
            next_node = state.next_node
            state.next_node = None
            return _node_value(next_node)

    current_agent = _node_value(state.current_agent)

    if state.mode == Mode.CHAT:
        if state.messages:
            last_message = state.messages[-1]
            if isinstance(last_message, dict) and last_message.get("role") == "assistant":
                return END
        return NextNode.CHAT.value

    if state.mode == Mode.PLANNING:
        if state.trigger_plan:
            return NextNode.PLANNER.value
        if state.interface_refresh:
            return NextNode.INTERFACE.value
        if current_agent == NextNode.PLANNER.value:
            return NextNode.INTERFACE.value
        if current_agent in {NextNode.INTERFACE.value, NextNode.ERROR.value}:
            return END

    if state.mode == Mode.EXECUTING:
        if state.next_node == NextNode.TESTER:
            return NextNode.TESTER.value
        if state.approval_required:
            return END
        if state.run_status in {
            RunStatus.WAITING_APPROVAL,
            RunStatus.BLOCKED,
            RunStatus.FAILED,
            RunStatus.SUCCESS,
        }:
            return END
        if state.run_status == RunStatus.RUNNING:
            return NextNode.CODER.value
        return END

    return END
