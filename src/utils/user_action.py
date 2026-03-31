from agent.state import AgentState, UserAction, NextNode, Mode, PlanStatus, RunStatus
from utils.save_state import save_session_state


def handle_user_action(action: UserAction, state: AgentState):
    if action == UserAction.SAVE_PLAN:
        save_session_state(state)
        state.next_node = None  # stay in current node or UI
        return state

    if action == UserAction.REGENERATE_PLAN:
        state.mode = Mode.PLANNING
        state.trigger_plan = True
        state.next_node = NextNode.PLANNER
        state.plan_status = PlanStatus.DRAFT
        state.run_status = RunStatus.RUNNING
        state.approval_required = False
        state.approval_type = None
        state.approval_payload = None
        return state

    if action == UserAction.GO_INTERFACE:
        state.mode = Mode.PLANNING
        state.trigger_plan = False
        state.next_node = NextNode.INTERFACE
        state.interface_refresh = True
        state.run_status = RunStatus.RUNNING
        state.approval_required = False
        state.approval_type = None
        state.approval_payload = None
        return state

    if action == UserAction.GENERATE_PLAN:
        state.mode = Mode.PLANNING
        state.trigger_plan = True
        state.next_node = NextNode.PLANNER
        state.plan_status = PlanStatus.DRAFT
        state.run_status = RunStatus.RUNNING
        state.approval_required = False
        state.approval_type = None
        state.approval_payload = None
        return state

    if action == UserAction.CONTINUE_CHAT:
        state.mode = Mode.CHAT
        state.trigger_plan = False
        state.next_node = NextNode.CHAT
        state.run_status = RunStatus.IDLE
        state.approval_required = False
        state.approval_type = None
        state.approval_payload = None
        return state

    if action == UserAction.MODIFY_PLAN:
        state.mode = Mode.PLANNING
        state.trigger_plan = True
        state.next_node = NextNode.PLANNER
        state.plan_status = PlanStatus.DRAFT
        state.run_status = RunStatus.RUNNING
        state.approval_required = False
        state.approval_type = None
        state.approval_payload = None
        return state

    if action == UserAction.EXECUTE_PLAN:
        state.mode = Mode.EXECUTING
        state.plan_status = PlanStatus.APPROVED
        state.run_status = RunStatus.RUNNING
        state.trigger_plan = False
        state.interface_refresh = False
        state.next_node = None
        state.approval_required = False
        state.approval_type = None
        state.approval_payload = None
        state.current_step_id = None
        state.current_step_title = None
        state.last_action_summary = None
        state.last_validation_summary = None
        state.last_validation_status = None
        state.last_validation_passed = None
        state.last_failure_category = None
        state.last_evidence = []
        state.last_outcome = None
        return state

    return state
