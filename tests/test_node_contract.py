"""Tests for node_contract mechanical enforcement.

Verifies that assert_execution_node_contract catches missing fields and
passes on complete return dicts. Also spot-checks real node return paths
to confirm they satisfy the contract.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from utils.node_contract import assert_execution_node_contract, NodeContractViolation, EXECUTION_NODE_REQUIRED_FIELDS


def _minimal_valid_result():
    """A return dict that satisfies the execution node contract."""
    return {
        "run_status": "running",
        "last_outcome": "success",
        "last_evidence": [],
        "current_agent": "coder",
        "next_node": None,
    }


def test_valid_result_passes():
    result = _minimal_valid_result()
    assert_execution_node_contract(result, "test_node")  # must not raise
    print("PASS: valid result passes")


def test_extra_fields_are_allowed():
    result = _minimal_valid_result()
    result["plan"] = []
    result["progress_text"] = "doing work"
    assert_execution_node_contract(result, "test_node")  # must not raise
    print("PASS: extra fields are allowed")


def test_missing_run_status_raises():
    result = _minimal_valid_result()
    del result["run_status"]
    try:
        assert_execution_node_contract(result, "coder")
        raise AssertionError("Expected NodeContractViolation")
    except NodeContractViolation as e:
        assert "run_status" in str(e)
        assert "coder" in str(e)
    print("PASS: missing run_status raises")


def test_missing_last_outcome_raises():
    result = _minimal_valid_result()
    del result["last_outcome"]
    try:
        assert_execution_node_contract(result, "tester")
        raise AssertionError("Expected NodeContractViolation")
    except NodeContractViolation as e:
        assert "last_outcome" in str(e)
    print("PASS: missing last_outcome raises")


def test_missing_last_evidence_raises():
    result = _minimal_valid_result()
    del result["last_evidence"]
    try:
        assert_execution_node_contract(result, "tester")
        raise AssertionError("Expected NodeContractViolation")
    except NodeContractViolation as e:
        assert "last_evidence" in str(e)
    print("PASS: missing last_evidence raises")


def test_missing_multiple_fields_reports_all():
    result = {"run_status": "running"}  # only one field present
    try:
        assert_execution_node_contract(result, "coder")
        raise AssertionError("Expected NodeContractViolation")
    except NodeContractViolation as e:
        msg = str(e)
        assert "last_outcome" in msg
        assert "last_evidence" in msg
        assert "current_agent" in msg
        assert "next_node" in msg
    print("PASS: all missing fields reported together")


def test_coder_node_success_path_satisfies_contract(monkeypatch=None, tmp_path=None):
    """Spot-check: coder_node success return dict contains all required fields."""
    import pathlib, tempfile
    from agent.nodes import coder_node as coder_module
    from agent.state import AgentState, Mode, RunStatus, Interface, Parameter, Step, StepStatus

    tmp = pathlib.Path(tempfile.mkdtemp())

    step = Step(
        id="R001-S01",
        description="build login ui",
        implementation_file="src/generated_contract_check.py",
        status=StepStatus.PENDING,
        interface=Interface(
            name="build_login_ui",
            parameters=[Parameter(name="username", type="str")],
            return_type="None",
            description="Build login UI",
            dependencies=[],
        ),
    )

    calls = {"gpt": 0}

    def fake_call_gpt(*, messages, **kwargs):
        calls["gpt"] += 1
        return {"choices": [{"message": {"content": "```python\ndef build_login_ui(username: str) -> None:\n    return None\n```"}}]}

    def fake_write_file(path: str, content: str) -> str:
        target = tmp / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"File written successfully: {path}"

    original_call_gpt = coder_module.call_gpt
    original_write_file = coder_module.write_file
    original_skeleton = coder_module.get_workspace_skeleton_direct
    coder_module.call_gpt = fake_call_gpt
    coder_module.write_file = fake_write_file
    coder_module.get_workspace_skeleton_direct = lambda workspace_root: "skeleton"

    try:
        state = AgentState(
            session_id="test",
            mode=Mode.EXECUTING,
            run_status=RunStatus.RUNNING,
            workspace_root=str(tmp),
            plan=[step],
        )
        result = coder_module.coder_node(state)
        assert_execution_node_contract(result, "coder_node")
        print("PASS: coder_node success path satisfies contract")
    finally:
        coder_module.call_gpt = original_call_gpt
        coder_module.write_file = original_write_file
        coder_module.get_workspace_skeleton_direct = original_skeleton


def test_tester_node_success_path_satisfies_contract(tmp_path=None):
    """Spot-check: tester_node success return dict contains all required fields."""
    import pathlib, tempfile
    from agent.nodes import tester_node as tester_module
    from agent.state import AgentState, Mode, RunStatus, Interface, Parameter, Step, StepStatus

    tmp = pathlib.Path(tempfile.mkdtemp())
    impl_file = "src/generated_contract_tester.py"
    target = tmp / impl_file
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("def build_login_ui(username: str) -> None:\n    return None\n", encoding="utf-8")

    step = Step(
        id="R001-S01",
        description="build login ui",
        implementation_file=impl_file,
        status=StepStatus.RUNNING,
        interface=Interface(
            name="build_login_ui",
            parameters=[Parameter(name="username", type="str")],
            return_type="None",
            description="Build login UI",
            dependencies=[],
        ),
    )

    state = AgentState(
        session_id="test",
        mode=Mode.EXECUTING,
        run_status=RunStatus.RUNNING,
        workspace_root=str(tmp),
        plan=[step],
        current_step_id=step.id,
    )
    result = tester_module.tester_node(state)
    assert_execution_node_contract(result, "tester_node")
    print("PASS: tester_node success path satisfies contract")


def test_tester_node_retry_path_satisfies_contract(tmp_path=None):
    """Spot-check: tester_node retry return dict contains all required fields."""
    import pathlib, tempfile
    from agent.nodes import tester_node as tester_module
    from agent.state import AgentState, Mode, RunStatus, Interface, Parameter, Step, StepStatus

    tmp = pathlib.Path(tempfile.mkdtemp())
    impl_file = "src/generated_contract_retry.py"
    target = tmp / impl_file
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("def something_else() -> None:\n    return None\n", encoding="utf-8")

    step = Step(
        id="R001-S01",
        description="build login ui",
        implementation_file=impl_file,
        status=StepStatus.RUNNING,
        interface=Interface(
            name="build_login_ui",
            parameters=[Parameter(name="username", type="str")],
            return_type="None",
            description="Build login UI",
            dependencies=[],
        ),
    )

    state = AgentState(
        session_id="test",
        mode=Mode.EXECUTING,
        run_status=RunStatus.RUNNING,
        workspace_root=str(tmp),
        plan=[step],
        current_step_id=step.id,
    )
    result = tester_module.tester_node(state)
    assert_execution_node_contract(result, "tester_node")
    print("PASS: tester_node retry path satisfies contract")


if __name__ == "__main__":
    test_valid_result_passes()
    test_extra_fields_are_allowed()
    test_missing_run_status_raises()
    test_missing_last_outcome_raises()
    test_missing_last_evidence_raises()
    test_missing_multiple_fields_reports_all()
    test_coder_node_success_path_satisfies_contract()
    test_tester_node_success_path_satisfies_contract()
    test_tester_node_retry_path_satisfies_contract()
    print("\nAll contract enforcement tests passed.")
    sys.exit(0)
