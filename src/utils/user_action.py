

from agent.nodes.interface_build_node import interface_node
from agent.nodes.planner_node import planner_node
from agent.nodes.interface_build_node import interface_node
from agent.nodes import planner_node
from agent.state import AgentState, UserAction,NextNode

from utils.restore_state import load_latest_state
from utils.save_state import save_state
from utils.restore_state import load_latest_state
def handle_user_action(action: UserAction, state: AgentState):
    if action == UserAction.SAVE_PLAN:
        save_state(state)
        state.next_node = None  # stay in current node or UI
        return state

    if action == UserAction.REGENERATE_PLAN:
        state = load_latest_state(AgentState)
        state.next_node = NextNode.PLANNER
        return state

    if action == UserAction.GO_INTERFACE:
        state = load_latest_state(AgentState)
        state.next_node = NextNode.INTERFACE
        return state

    return state