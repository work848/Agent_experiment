from enum import Enum

from pydantic import BaseModel

from agent.state import AgentState, ActionGateType, ApprovalStatus, RunStatus, UserAction


class PolicyDecision(str, Enum):
    APPLY = "apply"
    REJECT = "reject"
    AWAIT_EXISTING_GATE = "await_existing_gate"


class PolicyResult(BaseModel):
    decision: PolicyDecision
    reason: str = ""


# Actions that are allowed even while an approval is pending (e.g. the user
# submitting the resolution itself is handled separately in main.py, but
# CONTINUE_CHAT is safe to pass through).
_GATE_EXEMPT_ACTIONS = {
    UserAction.CONTINUE_CHAT,
}


def evaluate_action(state: AgentState, action: UserAction) -> PolicyResult:
    """Return a PolicyResult describing whether the action should be applied."""

    # Explicit gate on state
    if state.action_gate is not None and state.action_gate.type != ActionGateType.NONE:
        return PolicyResult(
            decision=PolicyDecision.AWAIT_EXISTING_GATE,
            reason=f"Action gate active: {state.action_gate.type.value}"
            + (f" — {state.action_gate.message}" if state.action_gate.message else ""),
        )

    # Pending approvals gate (except exempt actions)
    if action not in _GATE_EXEMPT_ACTIONS:
        pending = [
            a for a in state.pending_approvals
            if a.status == ApprovalStatus.PENDING
        ]
        if pending:
            return PolicyResult(
                decision=PolicyDecision.AWAIT_EXISTING_GATE,
                reason=f"Pending approval must be resolved first (id={pending[0].id})",
            )

        # run_status gate
        if state.run_status == RunStatus.WAITING_APPROVAL:
            return PolicyResult(
                decision=PolicyDecision.AWAIT_EXISTING_GATE,
                reason="Run is waiting for approval; resolve the pending approval before sending actions",
            )

    # All UserAction values are explicitly handled — reaching here means APPLY
    if action not in set(UserAction):
        return PolicyResult(
            decision=PolicyDecision.REJECT,
            reason=f"Unknown action: {action}",
        )

    return PolicyResult(decision=PolicyDecision.APPLY)
