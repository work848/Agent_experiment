from agent.state import AgentState, UserAction, NextNode, Mode

from utils.restore_state import load_latest_state
from utils.save_state import save_state


def handle_user_action(action: UserAction, state: AgentState):
    if action == UserAction.SAVE_PLAN:
        save_state(state)
        state.next_node = None  # stay in current node or UI
        return state

    if action == UserAction.REGENERATE_PLAN:
        restored = load_latest_state(AgentState)
        if restored is not None:
            state = restored
        state.mode = Mode.PLANNING
        state.trigger_plan = True
        state.next_node = NextNode.PLANNER
        return state

    if action == UserAction.GO_INTERFACE:
        restored = load_latest_state(AgentState)
        if restored is not None:
            state = restored
        state.next_node = NextNode.INTERFACE
        return state

    if action == UserAction.GENERATE_PLAN:
        state.mode = Mode.PLANNING
        state.trigger_plan = True
        state.next_node = NextNode.PLANNER
        return state

    if action == UserAction.CONTINUE_CHAT:
        state.mode = Mode.CHAT
        state.trigger_plan = False
        state.next_node = NextNode.CHAT
        return state

    if action == UserAction.MODIFY_PLAN:
        state.mode = Mode.PLANNING
        state.trigger_plan = True
        state.next_node = NextNode.PLANNER
        return state

    return state
