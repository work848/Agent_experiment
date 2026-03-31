"""Integration test: all graph nodes working together.

Tests the full pipeline without real LLM calls where possible.
Run with:
    poetry run python src/run/test_integration.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.state import (
    AgentState, Mode, NextNode, RunStatus, PlanStatus,
    Step, Interface, Parameter, StepStatus, Requirement,
    RequirementStatus, ValidationStatus, StepOutcome,
    EvidenceRecord, ApprovalType,
)

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"


def check(label: str, condition: bool):
    print(f"  [{PASS if condition else FAIL}] {label}")
    if not condition:
        raise AssertionError(f"FAILED: {label}")


# ---------------------------------------------------------------------------
# 1. Graph compiles without errors
# ---------------------------------------------------------------------------
def test_graph_compiles():
    print("\n=== 1. Graph compiles ===")
    from agent.graph.build_graph import build_graph
    graph = build_graph()
    check("graph is not None", graph is not None)
    print("  Graph compiled successfully.")


# ---------------------------------------------------------------------------
# 2. Chat node: short message stays in chat mode
# ---------------------------------------------------------------------------
def test_chat_node_short_message():
    print("\n=== 2. chat_node: short message stays in chat ===")
    from agent.nodes.chat_node import chat_node
    state = AgentState(
        session_id="int-test-1",
        mode=Mode.CHAT,
        messages=[{"role": "user", "content": "hi"}],
    )
    result = chat_node(state)
    check("returns dict", isinstance(result, dict))
    # short message -> LLM chat response, not planning
    check("does not trigger plan", not result.get("trigger_plan", False))
    print(f"  ready_for_plan: {result.get('ready_for_plan')}")


# ---------------------------------------------------------------------------
# 3. Error node: retry path
# ---------------------------------------------------------------------------
def test_error_node_retry():
    print("\n=== 3. error_node: retry path ===")
    from agent.nodes.error_node import error_node
    state = AgentState(
        session_id="int-test-2",
        mode=Mode.PLANNING,
        last_failed_node=NextNode.PLANNER,
        last_error_message="planner failed",
        retry_count=0,
        max_node_retries=1,
    )
    result = error_node(state)
    check("trigger_plan=True on retry", result.get("trigger_plan") is True)
    check("retry_count incremented", result.get("retry_count") == 1)
    check("retrying_node=planner", result.get("retrying_node") == NextNode.PLANNER.value)
    check("run_status=RUNNING", result.get("run_status") == RunStatus.RUNNING)


# ---------------------------------------------------------------------------
# 4. Error node: exhausted retries -> approval required
# ---------------------------------------------------------------------------
def test_error_node_exhausted():
    print("\n=== 4. error_node: exhausted retries ===")
    from agent.nodes.error_node import error_node
    state = AgentState(
        session_id="int-test-3",
        mode=Mode.PLANNING,
        last_failed_node=NextNode.INTERFACE,
        last_error_message="interface failed",
        retry_count=1,
        max_node_retries=1,
    )
    result = error_node(state)
    check("approval_required=True", result.get("approval_required") is True)
    check("next_node=END", result.get("next_node") == NextNode.END)
    check("trigger_plan=False", not result.get("trigger_plan", False))


# ---------------------------------------------------------------------------
# 5. Coordinator: CHAT mode routes to chat
# ---------------------------------------------------------------------------
def test_coordinator_chat_mode():
    print("\n=== 5. coordinator: CHAT mode -> chat node ===")
    from agent.nodes.coordinator_node import central_coordinator
    state = AgentState(
        session_id="int-test-4",
        mode=Mode.CHAT,
        messages=[{"role": "user", "content": "hello"}],
    )
    result = central_coordinator(state)
    check("routes to chat", result == NextNode.CHAT.value)


# ---------------------------------------------------------------------------
# 6. Coordinator: PLANNING mode with trigger_plan -> planner
# ---------------------------------------------------------------------------
def test_coordinator_planning_trigger():
    print("\n=== 6. coordinator: trigger_plan -> planner ===")
    from agent.nodes.coordinator_node import central_coordinator
    state = AgentState(
        session_id="int-test-5",
        mode=Mode.PLANNING,
        trigger_plan=True,
    )
    result = central_coordinator(state)
    check("routes to planner", result == NextNode.PLANNER.value)


# ---------------------------------------------------------------------------
# 7. Coordinator: EXECUTING mode, RUNNING -> coder
# ---------------------------------------------------------------------------
def test_coordinator_executing_running():
    print("\n=== 7. coordinator: EXECUTING + RUNNING -> coder ===")
    from agent.nodes.coordinator_node import central_coordinator
    state = AgentState(
        session_id="int-test-6",
        mode=Mode.EXECUTING,
        run_status=RunStatus.RUNNING,
    )
    result = central_coordinator(state)
    check("routes to coder", result == NextNode.CODER.value)


# ---------------------------------------------------------------------------
# 8. Tester node: no plan -> blocked
# ---------------------------------------------------------------------------
def test_tester_no_plan():
    print("\n=== 8. tester_node: no plan -> BLOCKED ===")
    from agent.nodes.tester_node import tester_node
    state = AgentState(session_id="int-test-7")
    result = tester_node(state)
    check("run_status=BLOCKED", result["run_status"] == RunStatus.BLOCKED)
    check("last_outcome=BLOCKED", result["last_outcome"] == StepOutcome.BLOCKED)


# ---------------------------------------------------------------------------
# 9. Tester node: AST pass -> SUCCESS (no LLM needed)
# ---------------------------------------------------------------------------
def test_tester_ast_pass():
    print("\n=== 9. tester_node: AST pass -> SUCCESS ===")
    from agent.nodes.tester_node import tester_node
    with tempfile.TemporaryDirectory() as workspace:
        impl = os.path.join(workspace, "calc.py")
        with open(impl, "w") as f:
            f.write("def multiply(x, y):\n    return x * y\n")
        iface = Interface(
            name="multiply",
            parameters=[Parameter(name="x", type="int"), Parameter(name="y", type="int")],
            return_type="int",
            description="Multiply two numbers",
        )
        step = Step(
            id="R001-S01",
            description="Implement multiply",
            interface=iface,
            implementation_file="calc.py",
            status=StepStatus.RUNNING,
        )
        state = AgentState(
            session_id="int-test-8",
            plan=[step],
            current_step_id="R001-S01",
            workspace_root=workspace,
        )
        result = tester_node(state)
        check("validation_passed=True", result["last_validation_passed"] is True)
        check("outcome=SUCCESS", result["last_outcome"] == StepOutcome.SUCCESS)
        check("step marked SUCCESS", result["plan"][0].status == StepStatus.SUCCESS)
        check("has ast_symbol_check evidence", any(e.kind == "ast_symbol_check" for e in result["last_evidence"]))


# ---------------------------------------------------------------------------
# 10. Coder node: no plan -> blocked
# ---------------------------------------------------------------------------
def test_coder_no_plan():
    print("\n=== 10. coder_node: no plan -> BLOCKED ===")
    from agent.nodes.coder_node import coder_node
    state = AgentState(
        session_id="int-test-9",
        workspace_root="/tmp",
    )
    result = coder_node(state)
    check("run_status=BLOCKED", result["run_status"] == RunStatus.BLOCKED)


# ---------------------------------------------------------------------------
# 11. Full mini pipeline: tester -> (AST pass + pytest pass) -> SUCCESS
# ---------------------------------------------------------------------------
def test_full_mini_pipeline():
    print("\n=== 11. Full mini pipeline: coder result -> tester -> SUCCESS ===")
    from agent.nodes.tester_node import tester_node
    with tempfile.TemporaryDirectory() as workspace:
        # Simulate coder already wrote the file and generated a test
        impl = os.path.join(workspace, "adder.py")
        with open(impl, "w") as f:
            f.write("def add(a, b):\n    return a + b\n")

        tests_dir = os.path.join(workspace, "tests", "generated")
        os.makedirs(tests_dir, exist_ok=True)
        test_file = os.path.join(tests_dir, "test_adder.py")
        with open(test_file, "w") as f:
            f.write(
                "import sys, os\n"
                "sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))\n"
                "from adder import add\n"
                "def test_add_positive(): assert add(2, 3) == 5\n"
                "def test_add_zero(): assert add(0, 0) == 0\n"
            )

        iface = Interface(
            name="add",
            parameters=[Parameter(name="a", type="int"), Parameter(name="b", type="int")],
            return_type="int",
            description="Add two numbers",
        )
        step = Step(
            id="R001-S01",
            description="Implement add",
            interface=iface,
            implementation_file="adder.py",
            test_file="tests/generated/test_adder.py",
            status=StepStatus.RUNNING,
        )
        state = AgentState(
            session_id="int-test-10",
            plan=[step],
            current_step_id="R001-S01",
            workspace_root=workspace,
            mode=Mode.EXECUTING,
            run_status=RunStatus.RUNNING,
        )
        result = tester_node(state)
        check("validation_passed=True", result["last_validation_passed"] is True)
        check("outcome=SUCCESS", result["last_outcome"] == StepOutcome.SUCCESS)
        check("has pytest evidence", any(e.kind == "pytest_run" for e in result["last_evidence"]))
        check("pytest passed", all(e.passed for e in result["last_evidence"] if e.kind == "pytest_run"))
        check("run_status=SUCCESS (no more pending)", result["run_status"] == RunStatus.SUCCESS)
        print("  run_summary:", result.get("run_summary"))


if __name__ == "__main__":
    print("=" * 60)
    print("Integration Test — All Nodes")
    print("=" * 60)
    failed = []
    tests = [
        test_graph_compiles,
        test_chat_node_short_message,
        test_error_node_retry,
        test_error_node_exhausted,
        test_coordinator_chat_mode,
        test_coordinator_planning_trigger,
        test_coordinator_executing_running,
        test_tester_no_plan,
        test_tester_ast_pass,
        test_coder_no_plan,
        test_full_mini_pipeline,
    ]
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed.append(str(e))
        except Exception as e:
            failed.append(f"{t.__name__}: {type(e).__name__}: {e}")
            print(f"  [\033[91mERROR\033[0m] {e}")

    print("\n" + "=" * 60)
    if failed:
        print(f"FAILED ({len(failed)}/{len(tests)}):")
        for f in failed:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print(f"All {len(tests)} integration tests passed.")
    print("=" * 60)
