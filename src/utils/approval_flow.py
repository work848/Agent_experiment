from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel

from agent.state import ActionGate, ActionGateType, AgentState, ApprovalStatus, ApprovalType, Mode, RunStatus


class ApprovalDecision(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


class ApprovalResolution(BaseModel):
    approval_id: str
    decision: ApprovalDecision
    note: Optional[str] = None


def resolve_approval(state: AgentState, resolution: ApprovalResolution) -> AgentState:
    """Apply an approval resolution to state. Returns the mutated state."""

    target = next(
        (a for a in state.pending_approvals if a.id == resolution.approval_id),
        None,
    )
    if target is None:
        raise ValueError(f"No approval found with id={resolution.approval_id!r}")

    now = datetime.now(timezone.utc).isoformat()
    target.resolved_at = now
    target.resolution_note = resolution.note

    if resolution.decision == ApprovalDecision.APPROVED:
        target.status = ApprovalStatus.APPROVED
        # Clear gate fields
        state.action_gate = ActionGate(type=ActionGateType.NONE)
        state.approval_required = False
        state.approval_type = None
        state.approval_payload = None
        state.run_status = RunStatus.RUNNING
        # If this was an execute_plan approval, switch mode to EXECUTING
        if target.type == ApprovalType.EXECUTE_PLAN:
            state.mode = Mode.EXECUTING
        # If this was a retry_after_failure approval, reset the failed step to PENDING
        if target.type == ApprovalType.RETRY_AFTER_FAILURE and target.step_id and state.plan:
            from agent.state import StepStatus
            state.plan = [
                s.model_copy(update={"status": StepStatus.PENDING})
                if s.id == target.step_id else s
                for s in state.plan
            ]
    else:
        target.status = ApprovalStatus.REJECTED
        state.run_status = RunStatus.BLOCKED

    return state
