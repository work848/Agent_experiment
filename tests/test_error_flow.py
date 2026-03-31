from pathlib import Path

from agent.graph.build_graph import build_graph
from agent.nodes.error_node import error_node
from agent.nodes import coder_node as coder_module
from agent.nodes import interface_build_node as interface_module
from agent.nodes import planner_node as planner_module
from agent.nodes import tester_node as tester_module
from agent.nodes.coordinator_node import central_coordinator
from agent.state import (
    AgentState,
    ApprovalType,
    FailureCategory,
    Interface,
    Mode,
    NextNode,
    Parameter,
    Requirement,
    RunStatus,
    Step,
    StepOutcome,
    StepStatus,
    ValidationStatus,
)


def test_coordinator_routes_to_error_node():
    state = AgentState(
        session_id="session-1",
        mode=Mode.PLANNING,
        next_node=NextNode.ERROR,
    )

    assert central_coordinator(state) == "error"


def test_error_node_announces_retry_for_planner():
    state = AgentState(
        session_id="session-1",
        mode=Mode.PLANNING,
        messages=[],
        last_failed_node=NextNode.PLANNER,
        last_error_message="规划节点（planner）生成失败。",
        retry_count=0,
        max_node_retries=1,
    )

    result = error_node(state)

    assert result["next_node"] == NextNode.PLANNER
    assert result["trigger_plan"] is True
    assert result["retry_count"] == 1
    assert result["retrying_node"] == "planner"
    assert "正在自动重试 1/1" in result["messages"][-1]["content"]


def test_error_node_returns_final_message_after_retry_budget():
    state = AgentState(
        session_id="session-1",
        mode=Mode.PLANNING,
        messages=[],
        last_failed_node=NextNode.INTERFACE,
        last_error_message="接口节点（interface）生成失败。",
        retry_count=1,
        max_node_retries=1,
    )

    result = error_node(state)

    assert result["next_node"] == NextNode.END
    assert result["retrying_node"] is None
    assert "已自动重试一次，但仍未成功" in result["messages"][-1]["content"]


def test_graph_retries_planner_once(monkeypatch):
    graph = build_graph()
    requirement = Requirement(
        id="R001",
        title="用户登录",
        description="作为注册用户，我需要通过邮箱和密码登录系统。",
    )
    state = AgentState(
        session_id="session-1",
        mode=Mode.PLANNING,
        trigger_plan=True,
        requirements=[requirement],
        workspace_root="workspace",
    )

    calls = {"planner": 0, "interface": 0}

    def fake_planner_call(*, messages, **kwargs):
        calls["planner"] += 1
        if calls["planner"] == 1:
            return {"choices": [{"message": {"content": "not-json"}}]}
        return {
            "choices": [
                {
                    "message": {
                        "content": '{"plan": [{"id": "R001-S01", "description": "搭建登录页面 UI", "dependencies": []}]}'
                    }
                }
            ]
        }

    def fake_interface_call(*, messages, **kwargs):
        calls["interface"] += 1
        return {
            "choices": [
                {
                    "message": {
                        "content": '{"interfaces": [{"step_id": "R001-S01", "interface": {"name": "build_login_ui", "parameters": [], "return_type": "None", "description": "build login ui", "dependencies": []}}]}'
                    }
                }
            ]
        }

    monkeypatch.setattr(planner_module, "call_gpt", fake_planner_call)
    monkeypatch.setattr(interface_module, "call_gpt", fake_interface_call)
    monkeypatch.setattr(interface_module, "get_workspace_skeleton_direct", lambda workspace_root: "skeleton")

    result = graph.invoke(state, config={"recursion_limit": 5})

    assert calls["planner"] == 2
    assert len(result["plan"]) == 1
    assert result["plan"][0].interface is not None
    assert any("正在自动重试 1/1" in message["content"] for message in result["messages"] if message["role"] == "assistant")


def test_graph_stops_after_interface_retry_exhausted(monkeypatch):
    graph = build_graph()
    state = AgentState(
        session_id="session-1",
        mode=Mode.PLANNING,
        interface_refresh=True,
        workspace_root="workspace",
        plan=[Step(id="R001-S01", description="搭建登录页面 UI")],
    )

    def fake_interface_call(*, messages, **kwargs):
        return {"choices": [{"message": {"content": "not-json"}}]}

    monkeypatch.setattr(interface_module, "call_gpt", fake_interface_call)
    monkeypatch.setattr(interface_module, "get_workspace_skeleton_direct", lambda workspace_root: "skeleton")

    result = graph.invoke(state, config={"recursion_limit": 5})

    assert result["next_node"] == NextNode.END
    assert result["retrying_node"] is None
    assert result["retry_count"] == 1
    assert "已自动重试一次，但仍未成功" in result["messages"][-1]["content"]



def _build_execution_step(
    *,
    interface_name: str = "build_login_ui",
    implementation_file: str = "src/generated_login.py",
    status: StepStatus = StepStatus.PENDING,
    retries: int = 0,
):
    return Step(
        id="R001-S01",
        description="搭建登录页面 UI",
        implementation_file=implementation_file,
        status=status,
        retries=retries,
        interface=Interface(
            name=interface_name,
            parameters=[Parameter(name="username", type="str")],
            return_type="None",
            description="Build the login UI.",
            dependencies=[],
        ),
    )



def _write_workspace_file(workspace_root: Path, relative_path: str, content: str) -> None:
    target = workspace_root / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")



def test_coordinator_routes_running_execution_to_coder():
    state = AgentState(
        session_id="session-1",
        mode=Mode.EXECUTING,
        run_status=RunStatus.RUNNING,
    )

    assert central_coordinator(state) == "coder"



def test_coordinator_routes_execution_to_tester():
    state = AgentState(
        session_id="session-1",
        mode=Mode.EXECUTING,
        run_status=RunStatus.RUNNING,
        next_node=NextNode.TESTER,
    )

    assert central_coordinator(state) == "tester"



def test_coordinator_stops_on_terminal_execution_states():
    for status in (RunStatus.WAITING_APPROVAL, RunStatus.BLOCKED, RunStatus.SUCCESS):
        state = AgentState(
            session_id="session-1",
            mode=Mode.EXECUTING,
            run_status=status,
        )
        assert central_coordinator(state) == "__end__"



def test_graph_executes_single_step_success(monkeypatch, tmp_path):
    graph = build_graph()
    step = _build_execution_step(implementation_file="src/generated_success.py")

    def fake_call_gpt(*, messages, **kwargs):
        return {
            "choices": [
                {
                    "message": {
                        "content": "```python\ndef build_login_ui(username: str) -> None:\n    return None\n```"
                    }
                }
            ]
        }

    def fake_write_file(path: str, content: str) -> str:
        _write_workspace_file(tmp_path, path, content)
        return f"File written successfully: {path}"

    monkeypatch.setattr(coder_module, "call_gpt", fake_call_gpt)
    monkeypatch.setattr(coder_module, "get_workspace_skeleton_direct", lambda workspace_root: "skeleton")
    monkeypatch.setattr(coder_module, "write_file", fake_write_file)

    result = graph.invoke(
        AgentState(
            session_id="session-1",
            mode=Mode.EXECUTING,
            run_status=RunStatus.RUNNING,
            workspace_root=str(tmp_path),
            plan=[step],
        ),
        config={"recursion_limit": 8},
    )

    assert result["plan"][0].status == StepStatus.SUCCESS
    assert result["current_step_id"] == "R001-S01"
    assert result["current_step_title"] == "搭建登录页面 UI"
    assert "Implement step R001-S01" in result["last_action_summary"]
    assert result["last_validation_summary"].startswith("Validated build_login_ui in src/generated_success.py.")
    assert result["last_validation_status"] == ValidationStatus.PASSED
    assert result["last_validation_passed"] is True
    assert result["last_failure_category"] is None
    assert len(result["last_evidence"]) == 1
    assert result["last_evidence"][0].kind == "ast_symbol_check"
    assert result["last_evidence"][0].file_path == "src/generated_success.py"
    assert result["last_evidence"][0].symbol_name == "build_login_ui"
    assert result["last_outcome"] == StepOutcome.SUCCESS
    assert result["run_status"] == RunStatus.SUCCESS



def test_tester_requests_retry_before_budget_exhausted(tmp_path):
    step = _build_execution_step(
        implementation_file="src/generated_retry.py",
        status=StepStatus.RUNNING,
    )
    _write_workspace_file(tmp_path, step.implementation_file, "def something_else():\n    return None\n")

    result = tester_module.tester_node(
        AgentState(
            session_id="session-1",
            mode=Mode.EXECUTING,
            workspace_root=str(tmp_path),
            plan=[step],
            current_step_id=step.id,
        )
    )

    assert result["plan"][0].status == StepStatus.PENDING
    assert result["plan"][0].retries == 1
    assert result["next_node"] == NextNode.CODER
    assert result["run_status"] == RunStatus.RUNNING
    assert result["last_validation_status"] == ValidationStatus.FAILED
    assert result["last_failure_category"] == FailureCategory.MISSING_IMPLEMENTATION
    assert len(result["last_evidence"]) == 1
    assert result["last_evidence"][0].passed is False
    assert result["last_outcome"] == StepOutcome.RETRY
    assert result["retry_count"] == 1
    assert result["last_validation_passed"] is False



def test_graph_retries_once_then_succeeds(monkeypatch, tmp_path):
    graph = build_graph()
    step = _build_execution_step(implementation_file="src/generated_retry_then_success.py")
    calls = {"count": 0}

    def fake_call_gpt(*, messages, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            content = "```python\ndef placeholder() -> None:\n    return None\n```"
        else:
            content = "```python\ndef build_login_ui(username: str) -> None:\n    return None\n```"
        return {"choices": [{"message": {"content": content}}]}

    def fake_write_file(path: str, content: str) -> str:
        _write_workspace_file(tmp_path, path, content)
        return f"File written successfully: {path}"

    monkeypatch.setattr(coder_module, "call_gpt", fake_call_gpt)
    monkeypatch.setattr(coder_module, "get_workspace_skeleton_direct", lambda workspace_root: "skeleton")
    monkeypatch.setattr(coder_module, "write_file", fake_write_file)

    result = graph.invoke(
        AgentState(
            session_id="session-1",
            mode=Mode.EXECUTING,
            run_status=RunStatus.RUNNING,
            workspace_root=str(tmp_path),
            plan=[step],
        ),
        config={"recursion_limit": 12},
    )

    assert calls["count"] == 2
    assert result["plan"][0].status == StepStatus.SUCCESS
    assert result["plan"][0].retries == 1
    assert result["last_validation_status"] == ValidationStatus.PASSED
    assert result["last_validation_passed"] is True
    assert result["last_failure_category"] is None
    assert len(result["last_evidence"]) == 1
    assert result["last_outcome"] == StepOutcome.SUCCESS
    assert result["run_status"] == RunStatus.SUCCESS



def test_tester_escalates_after_retry_budget(tmp_path):
    step = _build_execution_step(
        implementation_file="src/generated_exhausted.py",
        status=StepStatus.RUNNING,
        retries=1,
    )
    _write_workspace_file(tmp_path, step.implementation_file, "def something_else():\n    return None\n")

    result = tester_module.tester_node(
        AgentState(
            session_id="session-1",
            mode=Mode.EXECUTING,
            workspace_root=str(tmp_path),
            plan=[step],
            current_step_id=step.id,
        )
    )

    assert result["plan"][0].status == StepStatus.FAILED
    assert result["plan"][0].retries == 2
    assert result["run_status"] == RunStatus.WAITING_APPROVAL
    assert result["approval_required"] is True
    assert result["approval_type"] == ApprovalType.RETRY_AFTER_FAILURE
    assert result["approval_payload"]["step_id"] == step.id
    assert result["approval_payload"]["retry_count"] == 2
    assert result["approval_payload"]["failure_category"] == FailureCategory.MISSING_IMPLEMENTATION.value
    assert result["last_validation_status"] == ValidationStatus.FAILED
    assert result["last_failure_category"] == FailureCategory.MISSING_IMPLEMENTATION
    assert len(result["last_evidence"]) == 1
    assert result["last_outcome"] == StepOutcome.WAITING_APPROVAL



def test_tester_returns_blocked_when_implementation_file_missing(tmp_path):
    step = _build_execution_step(
        implementation_file="src/missing_validation_target.py",
        status=StepStatus.RUNNING,
    )

    result = tester_module.tester_node(
        AgentState(
            session_id="session-1",
            mode=Mode.EXECUTING,
            workspace_root=str(tmp_path),
            plan=[step],
            current_step_id=step.id,
        )
    )

    assert result["run_status"] == RunStatus.BLOCKED
    assert result["last_validation_status"] == ValidationStatus.BLOCKED
    assert result["last_failure_category"] == FailureCategory.MISSING_FILE
    assert len(result["last_evidence"]) == 1
    assert result["last_outcome"] == StepOutcome.BLOCKED
    assert "Implementation file does not exist" in result["last_validation_summary"]
    assert result["plan"][0].status == StepStatus.FAILED



def test_coder_records_failure_evidence_when_codegen_output_is_invalid(monkeypatch, tmp_path):
    graph = build_graph()
    step = _build_execution_step(implementation_file="src/generated_invalid_codegen.py")

    def fake_call_gpt(*, messages, **kwargs):
        return {"choices": [{"message": {"content": "not-a-code-block"}}]}

    monkeypatch.setattr(coder_module, "call_gpt", fake_call_gpt)
    monkeypatch.setattr(coder_module, "get_workspace_skeleton_direct", lambda workspace_root: "skeleton")

    result = graph.invoke(
        AgentState(
            session_id="session-1",
            mode=Mode.EXECUTING,
            run_status=RunStatus.RUNNING,
            workspace_root=str(tmp_path),
            plan=[step],
        ),
        config={"recursion_limit": 8},
    )

    assert result["run_status"] == RunStatus.FAILED
    assert result["last_failure_category"] == FailureCategory.EXECUTION_ERROR
    assert len(result["last_evidence"]) == 1
    assert result["last_evidence"][0].kind == "codegen_response"
    assert result["last_outcome"] == StepOutcome.FAILED
    assert result["plan"][0].status == StepStatus.FAILED
    assert "valid python code block" in result["last_error_message"]
    assert result["last_validation_summary"] is None
    assert result["last_validation_status"] is None
    assert result["last_validation_passed"] is None
    assert result["next_node"] is None
    assert result["approval_required"] is False


# ---------------------------------------------------------------------------
# Approval lifecycle tests
# ---------------------------------------------------------------------------

def test_tester_escalation_creates_pending_approval(tmp_path):
    """After retry budget exhausted, pending_approvals should have one PENDING entry."""
    from agent.state import ApprovalStatus

    step = _build_execution_step(
        implementation_file="src/generated_exhausted2.py",
        status=StepStatus.RUNNING,
        retries=1,
    )
    _write_workspace_file(tmp_path, step.implementation_file, "def something_else():\n    return None\n")

    result = tester_module.tester_node(
        AgentState(
            session_id="session-1",
            mode=Mode.EXECUTING,
            workspace_root=str(tmp_path),
            plan=[step],
            current_step_id=step.id,
        )
    )

    assert result["run_status"] == RunStatus.WAITING_APPROVAL
    assert result["approval_required"] is True
    pending = result["pending_approvals"]
    assert len(pending) == 1
    assert pending[0].status == ApprovalStatus.PENDING


def test_resolve_approval_approved_sets_running(tmp_path):
    """After resolve_approval(APPROVED), run_status becomes RUNNING and gate is cleared."""
    from agent.state import ApprovalStatus, ActionGateType
    from utils.approval_flow import ApprovalDecision, ApprovalResolution, resolve_approval

    step = _build_execution_step(
        implementation_file="src/generated_exhausted3.py",
        status=StepStatus.RUNNING,
        retries=1,
    )
    _write_workspace_file(tmp_path, step.implementation_file, "def something_else():\n    return None\n")

    result = tester_module.tester_node(
        AgentState(
            session_id="session-1",
            mode=Mode.EXECUTING,
            workspace_root=str(tmp_path),
            plan=[step],
            current_step_id=step.id,
        )
    )

    state = AgentState(
        session_id="session-1",
        mode=Mode.EXECUTING,
        run_status=result["run_status"],
        approval_required=result["approval_required"],
        approval_type=result["approval_type"],
        approval_payload=result["approval_payload"],
        pending_approvals=result["pending_approvals"],
    )
    approval_id = state.pending_approvals[0].id
    state = resolve_approval(state, ApprovalResolution(approval_id=approval_id, decision=ApprovalDecision.APPROVED))

    assert state.run_status == RunStatus.RUNNING
    assert state.approval_required is False
    assert state.action_gate.type == ActionGateType.NONE
    assert state.pending_approvals[0].status == ApprovalStatus.APPROVED


def test_resolve_approval_rejected_sets_blocked(tmp_path):
    """After resolve_approval(REJECTED), run_status becomes BLOCKED."""
    from agent.state import ApprovalStatus
    from utils.approval_flow import ApprovalDecision, ApprovalResolution, resolve_approval

    step = _build_execution_step(
        implementation_file="src/generated_exhausted4.py",
        status=StepStatus.RUNNING,
        retries=1,
    )
    _write_workspace_file(tmp_path, step.implementation_file, "def something_else():\n    return None\n")

    result = tester_module.tester_node(
        AgentState(
            session_id="session-1",
            mode=Mode.EXECUTING,
            workspace_root=str(tmp_path),
            plan=[step],
            current_step_id=step.id,
        )
    )

    state = AgentState(
        session_id="session-1",
        mode=Mode.EXECUTING,
        run_status=result["run_status"],
        approval_required=result["approval_required"],
        approval_type=result["approval_type"],
        approval_payload=result["approval_payload"],
        pending_approvals=result["pending_approvals"],
    )
    approval_id = state.pending_approvals[0].id
    state = resolve_approval(state, ApprovalResolution(approval_id=approval_id, decision=ApprovalDecision.REJECTED))

    assert state.run_status == RunStatus.BLOCKED
    assert state.pending_approvals[0].status == ApprovalStatus.REJECTED


