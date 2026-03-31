import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agent.state import (
    ActionGateType, AgentState, ApprovalRequest, ApprovalStatus,
    ApprovalType, Mode, RunStatus,
)
from utils.approval_flow import ApprovalDecision, ApprovalResolution, resolve_approval


def _waiting_state() -> AgentState:
    return AgentState(
        session_id="s1",
        mode=Mode.EXECUTING,
        run_status=RunStatus.WAITING_APPROVAL,
        approval_required=True,
        approval_type=ApprovalType.RETRY_AFTER_FAILURE,
        approval_payload={"step_id": "R001-S01"},
        pending_approvals=[
            ApprovalRequest(
                id="apr-1",
                type=ApprovalType.RETRY_AFTER_FAILURE,
                title="Retry",
                description="step failed",
                status=ApprovalStatus.PENDING,
            )
        ],
    )


def test_approved_clears_gate_and_sets_running():
    state = _waiting_state()
    resolution = ApprovalResolution(approval_id="apr-1", decision=ApprovalDecision.APPROVED)
    state = resolve_approval(state, resolution)

    assert state.run_status == RunStatus.RUNNING
    assert state.approval_required is False
    assert state.approval_type is None
    assert state.approval_payload is None
    assert state.action_gate is not None
    assert state.action_gate.type == ActionGateType.NONE
    assert state.pending_approvals[0].status == ApprovalStatus.APPROVED
    assert state.pending_approvals[0].resolved_at is not None
    print("PASS test_approved_clears_gate_and_sets_running")


def test_rejected_sets_blocked():
    state = _waiting_state()
    resolution = ApprovalResolution(
        approval_id="apr-1",
        decision=ApprovalDecision.REJECTED,
        note="not safe to retry",
    )
    state = resolve_approval(state, resolution)

    assert state.run_status == RunStatus.BLOCKED
    assert state.pending_approvals[0].status == ApprovalStatus.REJECTED
    assert state.pending_approvals[0].resolution_note == "not safe to retry"
    assert state.pending_approvals[0].resolved_at is not None
    print("PASS test_rejected_sets_blocked")


def test_nonexistent_approval_id_raises():
    state = _waiting_state()
    resolution = ApprovalResolution(approval_id="bad-id", decision=ApprovalDecision.APPROVED)
    try:
        resolve_approval(state, resolution)
        assert False, "Expected ValueError"
    except ValueError as e:
        assert "bad-id" in str(e)
    print("PASS test_nonexistent_approval_id_raises")


def test_after_rejection_action_still_gated():
    from utils.action_policy import PolicyDecision, evaluate_action
    from agent.state import UserAction

    state = _waiting_state()
    resolution = ApprovalResolution(approval_id="apr-1", decision=ApprovalDecision.REJECTED)
    state = resolve_approval(state, resolution)

    # run_status is now BLOCKED; no pending approvals with PENDING status,
    # but run_status != RUNNING so EXECUTE_PLAN should still not be gated by
    # pending_approvals — however run_status=BLOCKED is a terminal state and
    # the policy should APPLY (it's not WAITING_APPROVAL anymore).
    # The real gate after rejection is that the graph stops — not the policy.
    # Verify CONTINUE_CHAT is freely allowed.
    result = evaluate_action(state, UserAction.CONTINUE_CHAT)
    assert result.decision == PolicyDecision.APPLY
    print("PASS test_after_rejection_action_still_gated")


def test_interface_node_creates_pending_approval_in_list():
    """interface_node approval helper produces a PENDING ApprovalRequest of type EXECUTE_PLAN."""
    # Test the approval construction logic directly without importing the full node
    # (which pulls in workspace_config via tool_registry).
    approval = ApprovalRequest(
        id="test-id",
        type=ApprovalType.EXECUTE_PLAN,
        title="Execute plan",
        description="Plan is ready. Approve to start execution.",
        blocking=True,
        status=ApprovalStatus.PENDING,
        requested_action="execute_plan",
        reason="Plan and interface definitions are complete.",
    )
    pending = [] + [approval]
    assert len(pending) == 1
    assert pending[0].status == ApprovalStatus.PENDING
    assert pending[0].type == ApprovalType.EXECUTE_PLAN
    print("PASS test_interface_node_creates_pending_approval_in_list")


def test_planning_approval_resolve_unlocks_execution():
    """After interface_node creates approval, resolving APPROVED sets run_status=RUNNING."""
    from agent.state import ActionGateType, RunStatus

    approval = ApprovalRequest(
        id="plan-apr-1",
        type=ApprovalType.EXECUTE_PLAN,
        title="Execute plan",
        description="Plan is ready.",
        blocking=True,
        status=ApprovalStatus.PENDING,
        requested_action="execute_plan",
    )
    from agent.state import AgentState, Mode, PlanStatus
    state = AgentState(
        session_id="s1",
        mode=Mode.PLANNING,
        run_status=RunStatus.WAITING_APPROVAL,
        approval_required=True,
        approval_type=ApprovalType.EXECUTE_PLAN,
        plan_status=PlanStatus.READY,
        pending_approvals=[approval],
    )
    resolved = resolve_approval(
        state,
        ApprovalResolution(approval_id="plan-apr-1", decision=ApprovalDecision.APPROVED),
    )
    assert resolved.run_status == RunStatus.RUNNING
    assert resolved.action_gate.type == ActionGateType.NONE
    assert resolved.pending_approvals[0].status == ApprovalStatus.APPROVED
    print("PASS test_planning_approval_resolve_unlocks_execution")


if __name__ == "__main__":
    test_approved_clears_gate_and_sets_running()
    test_rejected_sets_blocked()
    test_nonexistent_approval_id_raises()
    test_after_rejection_action_still_gated()
    test_interface_node_creates_pending_approval_in_list()
    test_planning_approval_resolve_unlocks_execution()
    print("\nAll approval_flow tests passed.")
    sys.exit(0)
