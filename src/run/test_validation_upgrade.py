"""Demo: Phase 5 Validation Upgrade — tests all new functionality.

Runs without pytest. Execute with:
    poetry run python src/run/test_validation_upgrade.py
"""
import os
import sys
import tempfile

# Make sure src/ is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.test_runner import run_pytest
from agent.state import (
    AgentState,
    Interface,
    Parameter,
    Step,
    StepStatus,
    NextNode,
    RunStatus,
    ValidationStatus,
    StepOutcome,
)
from agent.nodes.tester_node import tester_node

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"


def check(label: str, condition: bool):
    print(f"  [{PASS if condition else FAIL}] {label}")
    if not condition:
        raise AssertionError(f"FAILED: {label}")


# ---------------------------------------------------------------------------
# 1. test_runner — passing test
# ---------------------------------------------------------------------------
def demo_test_runner_pass():
    print("\n=== 1. test_runner: passing test ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = os.path.join(tmpdir, "test_pass.py")
        with open(test_file, "w") as f:
            f.write("def test_always_passes():\n    assert 1 + 1 == 2\n")
        result = run_pytest(test_file, tmpdir)
        print(f"  pytest output: {result.output[:300]}")
        check("passed=True", result.passed)
        check("return_code=0", result.return_code == 0)
        check("output contains 'passed'", "passed" in result.output.lower())
        print(f"  output snippet: {result.output[:120]}")


# ---------------------------------------------------------------------------
# 2. test_runner — failing test
# ---------------------------------------------------------------------------
def demo_test_runner_fail():
    print("\n=== 2. test_runner: failing test ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = os.path.join(tmpdir, "test_fail.py")
        with open(test_file, "w") as f:
            f.write("def test_always_fails():\n    assert 1 == 2\n")
        result = run_pytest(test_file, tmpdir)
        check("passed=False", not result.passed)
        check("return_code!=0", result.return_code != 0)
        check("output contains 'failed'", "failed" in result.output.lower())
        print(f"  output snippet: {result.output[:120]}")


# ---------------------------------------------------------------------------
# 3. tester_node: AST pass + pytest pass -> SUCCESS
# ---------------------------------------------------------------------------
def demo_tester_ast_and_pytest_pass():
    print("\n=== 3. tester_node: AST pass + pytest pass -> SUCCESS ===")
    with tempfile.TemporaryDirectory() as workspace:
        # Write a simple implementation
        impl_file = os.path.join(workspace, "add.py")
        with open(impl_file, "w") as f:
            f.write("def add(a, b):\n    return a + b\n")

        # Write a passing test
        tests_dir = os.path.join(workspace, "tests", "generated")
        os.makedirs(tests_dir, exist_ok=True)
        test_file_abs = os.path.join(tests_dir, "test_add.py")
        with open(test_file_abs, "w") as f:
            f.write(
                "import sys, os\n"
                "sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))\n"
                "from add import add\n"
                "def test_add():\n"
                "    assert add(1, 2) == 3\n"
            )

        iface = Interface(
            name="add",
            parameters=[Parameter(name="a", type="int"), Parameter(name="b", type="int")],
            return_type="int",
            description="Add two numbers",
        )
        step = Step(
            id="S01",
            description="Implement add",
            interface=iface,
            implementation_file="add.py",
            test_file="tests/generated/test_add.py",
            status=StepStatus.RUNNING,
        )
        state = AgentState(
            session_id="demo",
            plan=[step],
            current_step_id="S01",
            workspace_root=workspace,
        )
        result = tester_node(state)
        check("outcome=SUCCESS", result["last_outcome"] == StepOutcome.SUCCESS)
        check("validation_passed=True", result["last_validation_passed"] is True)
        check("has pytest_run evidence", any(e.kind == "pytest_run" for e in result["last_evidence"]))
        check("pytest evidence passed", all(e.passed for e in result["last_evidence"] if e.kind == "pytest_run"))


# ---------------------------------------------------------------------------
# 4. tester_node: AST pass + pytest fail -> retry
# ---------------------------------------------------------------------------
def demo_tester_ast_pass_pytest_fail():
    print("\n=== 4. tester_node: AST pass + pytest fail -> retry ===")
    with tempfile.TemporaryDirectory() as workspace:
        impl_file = os.path.join(workspace, "add.py")
        with open(impl_file, "w") as f:
            f.write("def add(a, b):\n    return a - b  # intentionally broken\n")

        tests_dir = os.path.join(workspace, "tests", "generated")
        os.makedirs(tests_dir, exist_ok=True)
        test_file_abs = os.path.join(tests_dir, "test_add_fail.py")
        with open(test_file_abs, "w") as f:
            f.write(
                "import sys, os\n"
                "sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))\n"
                "from add import add\n"
                "def test_add():\n"
                "    assert add(1, 2) == 3\n"
            )

        iface = Interface(
            name="add",
            parameters=[Parameter(name="a", type="int"), Parameter(name="b", type="int")],
            return_type="int",
            description="Add two numbers",
        )
        step = Step(
            id="S01",
            description="Implement add",
            interface=iface,
            implementation_file="add.py",
            test_file="tests/generated/test_add_fail.py",
            status=StepStatus.RUNNING,
        )
        state = AgentState(
            session_id="demo",
            plan=[step],
            current_step_id="S01",
            workspace_root=workspace,
        )
        result = tester_node(state)
        check("outcome=RETRY", result["last_outcome"] == StepOutcome.RETRY)
        check("validation_passed=False", result["last_validation_passed"] is False)
        check("next_node=CODER", result["next_node"] == NextNode.CODER)
        check("has pytest_run evidence", any(e.kind == "pytest_run" for e in result["last_evidence"]))


# ---------------------------------------------------------------------------
# 5. state.py: extra_interfaces and test_file fields exist
# ---------------------------------------------------------------------------
def demo_state_fields():
    print("\n=== 5. state.py: new fields on Step and InterfaceTask ===")
    from agent.state import InterfaceTask
    iface = Interface(
        name="foo",
        parameters=[],
        return_type="None",
        description="primary",
    )
    extra = Interface(
        name="bar",
        parameters=[],
        return_type="str",
        description="extra",
    )
    step = Step(id="S01", description="test", interface=iface, extra_interfaces=[extra], test_file="tests/generated/test_s01.py")
    check("Step.test_file set", step.test_file == "tests/generated/test_s01.py")
    check("Step.extra_interfaces set", len(step.extra_interfaces) == 1)
    check("Step.extra_interfaces[0].name=bar", step.extra_interfaces[0].name == "bar")

    task = InterfaceTask(step_id="S01", interface=iface, extra_interfaces=[extra])
    check("InterfaceTask.extra_interfaces set", len(task.extra_interfaces) == 1)


if __name__ == "__main__":
    print("=" * 60)
    print("Phase 5 Validation Upgrade — Demo")
    print("=" * 60)
    try:
        demo_state_fields()
        demo_test_runner_pass()
        demo_test_runner_fail()
        demo_tester_ast_and_pytest_pass()
        demo_tester_ast_pass_pytest_fail()
        print("\n" + "=" * 60)
        print("All demos passed.")
        print("=" * 60)
    except AssertionError as e:
        print(f"\n{e}")
        sys.exit(1)
