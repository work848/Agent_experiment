import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agent.state import (
    ActionGate, ActionGateType, AgentState, ApprovalRequest, ApprovalStatus,
    ApprovalType, Mode, RunStatus, UserAction,
)
from utils.action_policy import PolicyDecision, evaluate_action


def _idle_state():
    return AgentState(session_id="s1", mode=Mode.CHAT, run_status=RunStatus.IDLE)


def _waiting_state():
    return AgentState(
        session_id="s1",
        mode=Mode.EXECUTING,
        run_status=RunStatus.WAITING_APPROVAL,
        approval_required=True,
        approval_type=ApprovalType.RETRY_AFTER_FAILURE,
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


def test_all_actions_allowed_in_idle_state():
    state = _idle_state()
    for action in UserAction:
        result = evaluate_action(state, action)
        assert result.decision == PolicyDecision.APPLY, (
            f"{action} should be APPLY in idle state, got {result.decision}: {result.reason}"
        )
    print("PASS test_all_actions_allowed_in_idle_state")


def test_actions_gated_when_pending_approval_exists():
    state = _waiting_state()
    gated_actions = [
        UserAction.EXECUTE_PLAN,
        UserAction.GENERATE_PLAN,
        UserAction.MODIFY_PLAN,
        UserAction.REGENERATE_PLAN,
        UserAction.GO_INTERFACE,
        UserAction.SAVE_PLAN,
    ]
    for action in gated_actions:
        result = evaluate_action(state, action)
        assert result.decision == PolicyDecision.AWAIT_EXISTING_GATE, (
            f"{action} should be AWAIT_EXISTING_GATE, got {result.decision}: {result.reason}"
        )
    print("PASS test_actions_gated_when_pending_approval_exists")


def test_continue_chat_exempt_from_pending_approval_gate():
    state = _waiting_state()
    result = evaluate_action(state, UserAction.CONTINUE_CHAT)
    assert result.decision == PolicyDecision.APPLY, (
        f"CONTINUE_CHAT should be APPLY even with pending approval, got {result.decision}"
    )
    print("PASS test_continue_chat_exempt_from_pending_approval_gate")


def test_action_gated_when_run_status_waiting_approval_no_pending():
    # run_status=WAITING_APPROVAL but pending_approvals list is empty
    state = AgentState(
        session_id="s1",
        mode=Mode.EXECUTING,
        run_status=RunStatus.WAITING_APPROVAL,
    )
    result = evaluate_action(state, UserAction.EXECUTE_PLAN)
    assert result.decision == PolicyDecision.AWAIT_EXISTING_GATE, (
        f"Expected AWAIT_EXISTING_GATE, got {result.decision}"
    )
    print("PASS test_action_gated_when_run_status_waiting_approval_no_pending")


def test_action_gated_when_action_gate_set():
    state = AgentState(
        session_id="s1",
        mode=Mode.EXECUTING,
        run_status=RunStatus.RUNNING,
        action_gate=ActionGate(
            type=ActionGateType.APPROVAL_REQUIRED,
            message="manual gate",
        ),
    )
    result = evaluate_action(state, UserAction.EXECUTE_PLAN)
    assert result.decision == PolicyDecision.AWAIT_EXISTING_GATE, (
        f"Expected AWAIT_EXISTING_GATE, got {result.decision}"
    )
    print("PASS test_action_gated_when_action_gate_set")


def test_action_allowed_when_gate_type_is_none():
    state = AgentState(
        session_id="s1",
        mode=Mode.EXECUTING,
        run_status=RunStatus.RUNNING,
        action_gate=ActionGate(type=ActionGateType.NONE),
    )
    result = evaluate_action(state, UserAction.EXECUTE_PLAN)
    assert result.decision == PolicyDecision.APPLY, (
        f"Expected APPLY with NONE gate, got {result.decision}"
    )
    print("PASS test_action_allowed_when_gate_type_is_none")


if __name__ == "__main__":
    test_all_actions_allowed_in_idle_state()
    test_actions_gated_when_pending_approval_exists()
    test_continue_chat_exempt_from_pending_approval_gate()
    test_action_gated_when_run_status_waiting_approval_no_pending()
    test_action_gated_when_action_gate_set()
    test_action_allowed_when_gate_type_is_none()
    print("\nAll action_policy tests passed.")
    sys.exit(0)
