import sys
import os
import tempfile
import shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agent.state import (
    AgentState, ApprovalRequest, ApprovalStatus, ApprovalType,
    EvidenceRecord, Mode, RunStatus,
)
from utils.save_state import save_session_state
from utils.restore_state import load_session_state


def _make_state(session_id: str) -> AgentState:
    return AgentState(
        session_id=session_id,
        mode=Mode.EXECUTING,
        run_status=RunStatus.WAITING_APPROVAL,
        run_id="run-abc",
        approval_required=True,
        approval_type=ApprovalType.RETRY_AFTER_FAILURE,
        pending_approvals=[
            ApprovalRequest(
                id="apr-1",
                type=ApprovalType.RETRY_AFTER_FAILURE,
                title="Retry step",
                description="step failed after retries",
                status=ApprovalStatus.PENDING,
                reason="symbol not found",
            )
        ],
        last_evidence=[
            EvidenceRecord(kind="ast_symbol_check", summary="symbol missing", passed=False)
        ],
    )


def test_round_trip_preserves_fields(tmp_sessions_dir):
    state = _make_state("sess-roundtrip")
    save_session_state(state)
    loaded = load_session_state(AgentState, "sess-roundtrip")
    assert loaded is not None
    assert loaded.session_id == "sess-roundtrip"
    assert loaded.run_id == "run-abc"
    assert loaded.run_status == RunStatus.WAITING_APPROVAL
    assert loaded.approval_required is True
    assert loaded.approval_type == ApprovalType.RETRY_AFTER_FAILURE
    assert len(loaded.pending_approvals) == 1
    assert loaded.pending_approvals[0].id == "apr-1"
    assert loaded.pending_approvals[0].status == ApprovalStatus.PENDING
    assert loaded.pending_approvals[0].reason == "symbol not found"
    assert len(loaded.last_evidence) == 1
    assert loaded.last_evidence[0].passed is False
    print("PASS test_round_trip_preserves_fields")


def test_two_sessions_do_not_collide(tmp_sessions_dir):
    state_a = _make_state("sess-a")
    state_b = _make_state("sess-b")
    state_b.run_id = "run-xyz"
    save_session_state(state_a)
    save_session_state(state_b)

    loaded_a = load_session_state(AgentState, "sess-a")
    loaded_b = load_session_state(AgentState, "sess-b")
    assert loaded_a.run_id == "run-abc"
    assert loaded_b.run_id == "run-xyz"
    print("PASS test_two_sessions_do_not_collide")


def test_missing_session_returns_none():
    result = load_session_state(AgentState, "nonexistent-session-xyz")
    assert result is None
    print("PASS test_missing_session_returns_none")


if __name__ == "__main__":
    # Use a temp dir to avoid polluting real state
    tmp = tempfile.mkdtemp()
    sessions_dir = os.path.join("src", "memory", "state", "sessions")
    os.makedirs(sessions_dir, exist_ok=True)

    try:
        test_round_trip_preserves_fields(sessions_dir)
        test_two_sessions_do_not_collide(sessions_dir)
        test_missing_session_returns_none()
        print("\nAll state_persistence tests passed.")
        sys.exit(0)
    finally:
        # Clean up test session files
        for sid in ["sess-roundtrip", "sess-a", "sess-b"]:
            path = os.path.join(sessions_dir, f"{sid}.json")
            if os.path.exists(path):
                os.remove(path)
