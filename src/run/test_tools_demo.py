"""Demo: test all registered agent tools.

Run with:
    poetry run python src/run/test_tools_demo.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config.workspace_config import WORKSPACE

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"


def check(label: str, condition: bool):
    print(f"  [{PASS if condition else FAIL}] {label}")
    if not condition:
        raise AssertionError(f"FAILED: {label}")


# ---------------------------------------------------------------------------
# 1. write_file
# ---------------------------------------------------------------------------
def demo_write_file():
    print("\n=== 1. write_file ===")
    from tools.write_file_tool import write_file
    result = write_file("tests/generated/_tool_test_write.py", "x = 1\n")
    check("returns success", "successfully" in result.lower())
    full = os.path.join(WORKSPACE, "tests/generated/_tool_test_write.py")
    check("file exists", os.path.exists(full))
    check("content correct", open(full).read() == "x = 1\n")
    print(f"  result: {result}")


# ---------------------------------------------------------------------------
# 2. apply_patch
# ---------------------------------------------------------------------------
def demo_apply_patch():
    print("\n=== 2. apply_patch ===")
    from tools.apply_patch import apply_patch
    # Set up a 3-line file
    target = "tests/generated/_tool_test_patch.py"
    full = os.path.join(WORKSPACE, target)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w") as f:
        f.write("line1\nline2\nline3\n")
    result = apply_patch(target, "2", "2", "replaced_line2\n")
    check("returns PATCH APPLIED", "PATCH APPLIED" in result)
    content = open(full).read()
    check("line2 replaced", "replaced_line2" in content)
    check("line1 preserved", content.startswith("line1"))
    check("line3 preserved", content.strip().endswith("line3"))
    print(f"  result: {result}")
    print(f"  file content: {repr(content)}")


# ---------------------------------------------------------------------------
# 3. read_file
# ---------------------------------------------------------------------------
def demo_read_file():
    print("\n=== 3. read_file ===")
    from tools.read_file import read_file
    target = "tests/generated/_tool_test_write.py"
    result = read_file(target)
    check("returns content", "x = 1" in result)
    print(f"  result: {repr(result[:80])}")


# ---------------------------------------------------------------------------
# 4. list_files
# ---------------------------------------------------------------------------
def demo_list_files():
    print("\n=== 4. list_files ===")
    from tools.list_files_tool import list_files
    result = list_files()
    check("returns file listing", len(result) > 0)
    check("contains py files", ".py" in result)
    print(f"  result snippet: {result[:200]}")


# ---------------------------------------------------------------------------
# 5. search_code
# ---------------------------------------------------------------------------
def demo_search_code():
    print("\n=== 5. search_code ===")
    from tools.search_code import search_code
    # search_code scans WORKSPACE (agent's target dir), not project source
    result = search_code("def ")
    check("returns a string", isinstance(result, str))
    check("non-empty result or no-matches msg", len(result) > 0)
    print(f"  result snippet: {result[:200]}")


# ---------------------------------------------------------------------------
# 6. load_tools — verify all tools register without error
# ---------------------------------------------------------------------------
def demo_load_tools():
    print("\n=== 6. load_tools — all tools register ===")
    from tools.base_tool import REGISTERED_TOOLS
    from tools.load_tools import load_all_tools
    before = len(REGISTERED_TOOLS)
    load_all_tools()
    names = list({s["function"]["name"] for s, _ in REGISTERED_TOOLS})  # dedupe
    print(f"  registered (unique): {sorted(names)}")
    check("apply_patch registered", "apply_patch" in names)
    check("read_file registered", "read_file" in names)
    check("list_files registered", "list_files" in names)
    check("search_code registered", "search_code" in names)
    check("run_python registered", "run_python" in names)
    # write_file uses no @tool decorator — it is called directly by coder_node, not via tool registry
    print("  (write_file is called directly, not via tool registry - by design)")


if __name__ == "__main__":
    print("=" * 60)
    print("Agent Tools Demo")
    print("=" * 60)
    try:
        demo_write_file()
        demo_apply_patch()
        demo_read_file()
        demo_list_files()
        demo_search_code()
        demo_load_tools()
        print("\n" + "=" * 60)
        print("All tool demos passed.")
        print("=" * 60)
    except AssertionError as e:
        print(f"\n{e}")
        sys.exit(1)
