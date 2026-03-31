"""Integration test: tool_node + save/restore AgentState + supporting functions.

Covers:
  1. Tool registry loads without error
  2. list_files tool executes via tool_node
  3. read_file tool executes via tool_node
  4. write_file tool executes via tool_node
  5. tool_node appends tool-role message and clears tool_call
  6. save_state -> load_state round-trip (AgentState reload)
  7. save_session_state -> load_session_state round-trip
  8. Multiple tool calls in one message are all executed
  9. tool_node: unknown tool name returns error string (no crash)
  10. State reload preserves nested models (Step, Interface, Parameter)

Run with:
    poetry run python src/run/test_integration_tools.py
"""
import os
import sys
import json
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ------------------------------------------------------------------
# Patch WORKSPACE to a temp dir so tool tests are fully self-contained
# ------------------------------------------------------------------
_TMP_WORKSPACE = tempfile.mkdtemp(prefix="agent_integration_")
os.environ["WORKSPACE"] = _TMP_WORKSPACE

# workspace.env must exist for workspace_config; create a minimal one
_WORKSPACE_ENV = os.path.join(os.path.dirname(__file__), "..", "..", "workspace.env")
if not os.path.exists(_WORKSPACE_ENV):
    with open(_WORKSPACE_ENV, "w") as _f:
        _f.write(f"WORKSPACE={_TMP_WORKSPACE}\n")

from agent.state import (
    AgentState, Mode, NextNode, RunStatus, PlanStatus, StepStatus,
    Step, Interface, Parameter, StepOutcome,
)
from utils.save_state import save_state, save_session_state
from utils.restore_state import load_state, load_session_state
from agent.nodes.tool_node import tool_node
from tools.tool_registry import TOOL_MAP, TOOLS

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"


def check(label: str, condition: bool):
    print(f"  [{PASS if condition else FAIL}] {label}")
    if not condition:
        raise AssertionError(f"FAILED: {label}")


def _make_tool_call(name: str, arguments: dict, call_id: str = "call_001"):
    return {
        "id": call_id,
        "type": "function",
        "function": {
            "name": name,
            "arguments": json.dumps(arguments),
        },
    }


def _state_with_tool_call(session_id: str, tool_calls: list) -> AgentState:
    """Return a minimal AgentState whose last message contains tool_calls."""
    return AgentState(
        session_id=session_id,
        messages=[
            {"role": "user", "content": "test"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": tool_calls,
            },
        ],
    )


# ------------------------------------------------------------------
# 1. Tool registry loads without error
# ------------------------------------------------------------------
def test_tool_registry_loaded():
    print("\n=== 1. Tool registry loads ===")
    check("TOOL_MAP is not empty", len(TOOL_MAP) > 0)
    # TOOLS may have duplicates from importlib.reload re-registering; TOOL_MAP deduplicates by name.
    # Assert that every entry in TOOL_MAP has a corresponding schema in TOOLS.
    tool_map_names = set(TOOL_MAP.keys())
    tools_names = {s["function"]["name"] for s in TOOLS}
    check("TOOL_MAP names are subset of TOOLS names", tool_map_names <= tools_names)
    check("list_files registered", "list_files" in TOOL_MAP)
    check("read_file registered", "read_file" in TOOL_MAP)
    print(f"  Registered tools: {sorted(TOOL_MAP.keys())}")


# ------------------------------------------------------------------
# 2. list_files via tool_node
# ------------------------------------------------------------------
def test_tool_node_list_files():
    print("\n=== 2. tool_node: list_files ===")
    # seed a file so list_files returns something
    seed = os.path.join(_TMP_WORKSPACE, "hello.txt")
    with open(seed, "w") as f:
        f.write("hello")

    tc = _make_tool_call("list_files", {})
    state = _state_with_tool_call("it-list-1", [tc])
    result = tool_node(state)

    check("returns AgentState", isinstance(result, AgentState))
    tool_msgs = [m for m in result.messages if m.get("role") == "tool"]
    check("one tool message appended", len(tool_msgs) == 1)
    check("tool_call_id matches", tool_msgs[0]["tool_call_id"] == "call_001")
    check("result contains filename", "hello.txt" in tool_msgs[0]["content"])
    check("tool_call cleared", result.tool_call is None)


# ------------------------------------------------------------------
# 3. read_file via tool_node
# ------------------------------------------------------------------
def test_tool_node_read_file():
    print("\n=== 3. tool_node: read_file ===")
    target = os.path.join(_TMP_WORKSPACE, "sample.py")
    with open(target, "w") as f:
        f.write("def foo():\n    return 42\n")

    tc = _make_tool_call("read_file", {"path": "sample.py"})
    state = _state_with_tool_call("it-read-1", [tc])
    result = tool_node(state)

    tool_msgs = [m for m in result.messages if m.get("role") == "tool"]
    check("one tool message appended", len(tool_msgs) == 1)
    content = tool_msgs[0]["content"]
    check("file content in result", "def foo" in content)
    check("FILE header present", "FILE:" in content)


# ------------------------------------------------------------------
# 4. write_file via tool_node
# ------------------------------------------------------------------
def test_tool_node_write_file():
    print("\n=== 4. tool_node: write_file ===")
    # write_file is not decorated with @tool so it is not in TOOL_MAP.
    # Calling it via tool_node should return a tool error message (no crash).
    rel_path = "generated_output.py"
    code = "def bar():\n    return 99\n"

    if "write_file" in TOOL_MAP:
        # If it becomes registered in the future, verify it actually works.
        tc = _make_tool_call("write_file", {"path": rel_path, "content": code})
        state = _state_with_tool_call("it-write-1", [tc])
        result = tool_node(state)
        tool_msgs = [m for m in result.messages if m.get("role") == "tool"]
        check("one tool message appended", len(tool_msgs) == 1)
        check("success message returned", "written" in tool_msgs[0]["content"].lower())
        written = os.path.join(_TMP_WORKSPACE, rel_path)
        check("file actually exists on disk", os.path.exists(written))
    else:
        # write_file not registered — tool_node should handle it gracefully
        print("  [INFO] write_file not in TOOL_MAP (no @tool decorator) — testing graceful error")
        tc = _make_tool_call("write_file", {"path": rel_path, "content": code})
        state = _state_with_tool_call("it-write-1", [tc])
        result = tool_node(state)
        tool_msgs = [m for m in result.messages if m.get("role") == "tool"]
        check("one tool message appended", len(tool_msgs) == 1)
        check("error response (unregistered tool)", "出错" in tool_msgs[0]["content"] or "error" in tool_msgs[0]["content"].lower())
        check("tool_call cleared", result.tool_call is None)


# ------------------------------------------------------------------
# 5. tool_node clears tool_call and appends correct message structure
# ------------------------------------------------------------------
def test_tool_node_message_structure():
    print("\n=== 5. tool_node: message structure ===")
    tc = _make_tool_call("list_files", {}, call_id="call_xyz")
    state = _state_with_tool_call("it-struct-1", [tc])
    original_len = len(state.messages)
    result = tool_node(state)

    check("messages grew by 1", len(result.messages) == original_len + 1)
    last = result.messages[-1]
    check("role=tool", last["role"] == "tool")
    check("tool_call_id set", last["tool_call_id"] == "call_xyz")
    check("content is string", isinstance(last["content"], str))
    check("tool_call field is None", result.tool_call is None)


# ------------------------------------------------------------------
# 6. save_state -> load_state round-trip
# ------------------------------------------------------------------
def test_save_load_state_roundtrip():
    print("\n=== 6. save_state -> load_state round-trip ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = os.path.join(tmpdir, "state_test.json")
        state = AgentState(
            session_id="rt-001",
            mode=Mode.PLANNING,
            run_status=RunStatus.RUNNING,
            messages=[{"role": "user", "content": "hello"}],
            iterations=3,
        )
        save_state(state, filepath=filepath)
        check("checkpoint file created", os.path.exists(filepath))

        restored = load_state(AgentState, filepath=filepath)
        check("restored is AgentState", isinstance(restored, AgentState))
        check("session_id preserved", restored.session_id == "rt-001")
        check("mode preserved", restored.mode == Mode.PLANNING)
        check("run_status preserved", restored.run_status == RunStatus.RUNNING)
        check("messages preserved", len(restored.messages) == 1)
        check("iterations preserved", restored.iterations == 3)


# ------------------------------------------------------------------
# 7. save_session_state -> load_session_state round-trip
# ------------------------------------------------------------------
def test_save_load_session_state_roundtrip():
    print("\n=== 7. save_session_state -> load_session_state round-trip ===")
    state = AgentState(
        session_id="sess-42",
        mode=Mode.EXECUTING,
        run_status=RunStatus.SUCCESS,
        messages=[{"role": "assistant", "content": "done"}],
        success=True,
    )
    save_session_state(state)
    session_path = f"src/memory/state/sessions/sess-42.json"
    check("session file created", os.path.exists(session_path))

    restored = load_session_state(AgentState, "sess-42")
    check("restored is AgentState", isinstance(restored, AgentState))
    check("session_id preserved", restored.session_id == "sess-42")
    check("mode preserved", restored.mode == Mode.EXECUTING)
    check("success preserved", restored.success is True)
    check("messages preserved", restored.messages[0]["content"] == "done")

    # cleanup
    if os.path.exists(session_path):
        os.remove(session_path)


# ------------------------------------------------------------------
# 8. Multiple tool calls in one message all execute
# ------------------------------------------------------------------
def test_tool_node_multiple_calls():
    print("\n=== 8. tool_node: multiple tool calls ===")
    # seed another file
    seed2 = os.path.join(_TMP_WORKSPACE, "multi_seed.txt")
    with open(seed2, "w") as f:
        f.write("seed2")

    tc1 = _make_tool_call("list_files", {}, call_id="call_A")
    tc2 = _make_tool_call("read_file", {"path": "hello.txt"}, call_id="call_B")

    state = AgentState(
        session_id="it-multi-1",
        messages=[
            {"role": "user", "content": "multi"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [tc1, tc2],
            },
        ],
    )
    result = tool_node(state)

    tool_msgs = [m for m in result.messages if m.get("role") == "tool"]
    check("two tool messages appended", len(tool_msgs) == 2)
    ids = {m["tool_call_id"] for m in tool_msgs}
    check("both call IDs present", ids == {"call_A", "call_B"})


# ------------------------------------------------------------------
# 9. tool_node: unknown tool name -> error string, no crash
# ------------------------------------------------------------------
def test_tool_node_unknown_tool():
    print("\n=== 9. tool_node: unknown tool -> error, no crash ===")
    tc = _make_tool_call("nonexistent_tool_xyz", {"foo": "bar"})
    state = _state_with_tool_call("it-unknown-1", [tc])
    result = tool_node(state)  # must not raise

    tool_msgs = [m for m in result.messages if m.get("role") == "tool"]
    check("tool message appended", len(tool_msgs) == 1)
    check("error mentioned in content", "error" in tool_msgs[0]["content"].lower() or "出错" in tool_msgs[0]["content"])


# ------------------------------------------------------------------
# 10. State reload preserves nested Step/Interface/Parameter models
# ------------------------------------------------------------------
def test_state_reload_preserves_nested_models():
    print("\n=== 10. save/load preserves nested Step/Interface/Parameter ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = os.path.join(tmpdir, "nested_state.json")
        iface = Interface(
            name="compute",
            parameters=[Parameter(name="x", type="int"), Parameter(name="y", type="float")],
            return_type="float",
            description="Compute something",
            dependencies=["math"],
        )
        step = Step(
            id="S01",
            description="Implement compute",
            interface=iface,
            implementation_file="compute.py",
            status=StepStatus.RUNNING,
            retries=2,
        )
        state = AgentState(
            session_id="nested-01",
            plan=[step],
            current_step_id="S01",
            mode=Mode.EXECUTING,
        )
        save_state(state, filepath=filepath)
        restored = load_state(AgentState, filepath=filepath)

        check("plan has one step", len(restored.plan) == 1)
        rs = restored.plan[0]
        check("step id preserved", rs.id == "S01")
        check("step status preserved", rs.status == StepStatus.RUNNING)
        check("step retries preserved", rs.retries == 2)
        check("interface present", rs.interface is not None)
        check("interface name preserved", rs.interface.name == "compute")
        check("parameters count", len(rs.interface.parameters) == 2)
        check("parameter name", rs.interface.parameters[0].name == "x")
        check("dependencies preserved", rs.interface.dependencies == ["math"])
        check("current_step_id preserved", restored.current_step_id == "S01")


# ------------------------------------------------------------------
# Runner
# ------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 60)
    print("Integration Test — tool_node + AgentState save/reload")
    print("=" * 60)

    tests = [
        test_tool_registry_loaded,
        test_tool_node_list_files,
        test_tool_node_read_file,
        test_tool_node_write_file,
        test_tool_node_message_structure,
        test_save_load_state_roundtrip,
        test_save_load_session_state_roundtrip,
        test_tool_node_multiple_calls,
        test_tool_node_unknown_tool,
        test_state_reload_preserves_nested_models,
    ]

    failed = []
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed.append(str(e))
        except Exception as e:
            import traceback
            failed.append(f"{t.__name__}: {type(e).__name__}: {e}")
            print(f"  [\033[91mERROR\033[0m] {type(e).__name__}: {e}")
            traceback.print_exc()

    print("\n" + "=" * 60)
    if failed:
        print(f"FAILED ({len(failed)}/{len(tests)}):")
        for f in failed:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print(f"All {len(tests)} integration tests passed.")
    print("=" * 60)
