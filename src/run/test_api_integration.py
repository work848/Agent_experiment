"""API integration test: POST /chat + GET /state + AgentState crash-reload.

Tests the live FastAPI server (must be running on localhost:8000).

Run backend first:
    poetry run uvicorn src.api.main:app --reload --port 8000

Then run this test:
    poetry run python src/run/test_api_integration.py
"""
import os
import sys
import json
import time

import requests

BASE = "http://localhost:8000"
SESSION_ID = f"api-test-{int(time.time())}"
WORKSPACE_ROOT = r"C:\temp\testFolder"

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"


def check(label: str, condition: bool, detail: str = ""):
    suffix = f" ({detail})" if detail else ""
    print(f"  [{PASS if condition else FAIL}] {label}{suffix}")
    if not condition:
        raise AssertionError(f"FAILED: {label}{suffix}")


def post_chat(payload: dict) -> requests.Response:
    return requests.post(f"{BASE}/chat", json=payload, timeout=60)


def get_state(session_id: str = None) -> requests.Response:
    params = {"session_id": session_id} if session_id else {}
    return requests.get(f"{BASE}/state", params=params, timeout=15)


# ------------------------------------------------------------------
# 0. Server reachable
# ------------------------------------------------------------------
def test_health():
    print("\n=== 0. GET / — health check ===")
    r = requests.get(f"{BASE}/", timeout=5)
    check("status 200", r.status_code == 200)
    check("status field present", "status" in r.json())
    print(f"  response: {r.json()}")


# ------------------------------------------------------------------
# 1. POST /chat — simple message, chat mode
# ------------------------------------------------------------------
def test_chat_simple_message():
    print("\n=== 1. POST /chat — simple message ===")
    payload = {
        "session_id": SESSION_ID,
        "message": "Hello, what can you help me with?",
        "mode": "chat",
        "workspace_root": WORKSPACE_ROOT,
    }
    r = post_chat(payload)
    check("status 200", r.status_code == 200, r.text[:200])
    body = r.json()
    check("messages present", "messages" in body)
    check("at least one message", len(body["messages"]) >= 1)
    check("run_status present", "run_status" in body)
    check("plan_status present", "plan_status" in body)
    print(f"  run_status: {body['run_status']}  plan_status: {body['plan_status']}")
    print(f"  last message role: {body['messages'][-1].get('role')}")
    return body


# ------------------------------------------------------------------
# 2. POST /chat — message that triggers requirement/planning readiness
# ------------------------------------------------------------------
def test_chat_requirement_message():
    print("\n=== 2. POST /chat — describe a feature (may trigger planning) ===")
    payload = {
        "session_id": SESSION_ID,
        "message": "I want to build a simple calculator that can add and subtract numbers.",
        "mode": "chat",
        "workspace_root": WORKSPACE_ROOT,
    }
    r = post_chat(payload)
    check("status 200", r.status_code == 200, r.text[:200])
    body = r.json()
    check("messages present", "messages" in body)
    check("agents field present", "agents" in body)
    check("ready_for_plan field present", "ready_for_plan" in body)
    print(f"  ready_for_plan: {body['ready_for_plan']}")
    print(f"  agents: {body['agents']}")
    return body


# ------------------------------------------------------------------
# 3. GET /state — state persisted after /chat calls
# ------------------------------------------------------------------
def test_get_state_after_chat():
    print("\n=== 3. GET /state — verify state was persisted ===")
    r = get_state(SESSION_ID)
    check("status 200", r.status_code == 200, r.text[:200])
    body = r.json()
    check("messages in state", "messages" in body)
    check("state has messages from chat", len(body.get("messages", [])) >= 1)
    check("plan_status present", "plan_status" in body)
    check("run_status present", "run_status" in body)
    print(f"  messages count: {len(body['messages'])}")
    print(f"  plan_status: {body['plan_status']}  run_status: {body['run_status']}")
    return body


# ------------------------------------------------------------------
# 4. Crash recovery: GET /state (no session_id) loads from disk
# ------------------------------------------------------------------
def test_crash_recovery_load_from_disk():
    print("\n=== 4. Crash recovery — GET /state loads persisted state from disk ===")
    # Calling without session_id forces the API to fall back to load_state() / load_latest_state()
    r = get_state()  # no session_id
    if r.status_code == 404:
        print("  [INFO] No global persisted state on disk — skipping disk-load check")
        print(f"  [{PASS}] graceful 404 when no disk state (expected on fresh server)")
        return None
    check("status 200", r.status_code == 200, r.text[:200])
    body = r.json()
    check("messages present", "messages" in body)
    check("run_status present", "run_status" in body)
    print(f"  Loaded state from disk. messages: {len(body['messages'])}  run_status: {body['run_status']}")
    return body


# ------------------------------------------------------------------
# 5. Tool use: POST /chat with list_files tool trigger
#    (The chat node calls the LLM which may invoke tools; we verify the
#     pipeline handles tool_calls → tool_node → result correctly)
# ------------------------------------------------------------------
def test_chat_tool_use_message():
    print("\n=== 5. POST /chat — message that may trigger tool use ===")
    payload = {
        "session_id": SESSION_ID,
        "message": "List the files in the project workspace for me.",
        "mode": "chat",
        "workspace_root": WORKSPACE_ROOT,
    }
    r = post_chat(payload)
    check("status 200", r.status_code == 200, r.text[:200])
    body = r.json()
    check("messages present", "messages" in body)
    msgs = body["messages"]
    roles = [m.get("role") for m in msgs]
    print(f"  message roles: {roles}")
    # If tool was used, there will be a 'tool' role message in history
    has_tool_msg = "tool" in roles
    has_assistant = "assistant" in roles
    check("assistant responded", has_assistant)
    if has_tool_msg:
        print("  [INFO] Tool message found — tool_node was invoked")
        tool_msgs = [m for m in msgs if m.get("role") == "tool"]
        check("tool message has content", all(m.get("content") for m in tool_msgs))
    else:
        print("  [INFO] No tool message — LLM chose not to call a tool (acceptable)")
    return body


# ------------------------------------------------------------------
# 6. State continuity: session carries forward between requests
# ------------------------------------------------------------------
def test_session_continuity():
    print("\n=== 6. Session continuity — messages accumulate ===")
    # First call
    r1 = post_chat({
        "session_id": SESSION_ID,
        "message": "My name is TestUser.",
        "mode": "chat",
        "workspace_root": WORKSPACE_ROOT,
    })
    check("first call 200", r1.status_code == 200)
    count1 = len(r1.json().get("messages", []))

    # Second call in same session
    r2 = post_chat({
        "session_id": SESSION_ID,
        "message": "What did I just tell you?",
        "mode": "chat",
        "workspace_root": WORKSPACE_ROOT,
    })
    check("second call 200", r2.status_code == 200)
    count2 = len(r2.json().get("messages", []))

    check("message count grew", count2 > count1, f"{count1} -> {count2}")
    print(f"  messages after call1={count1}, after call2={count2}")


# ------------------------------------------------------------------
# 7. POST /chat — bad payload (missing session_id) returns 422
# ------------------------------------------------------------------
def test_chat_bad_request():
    print("\n=== 7. POST /chat — missing session_id returns 422 ===")
    r = requests.post(f"{BASE}/chat", json={"message": "hi"}, timeout=10)
    check("status 422", r.status_code == 422, f"got {r.status_code}")


# ------------------------------------------------------------------
# 8. GET /state — unknown session_id falls back or 404
# ------------------------------------------------------------------
def test_get_state_unknown_session():
    print("\n=== 8. GET /state — unknown session falls back to disk or 404 ===")
    r = get_state("nonexistent-session-xyz-99999")
    check("200 or 404", r.status_code in {200, 404}, f"got {r.status_code}")
    print(f"  status: {r.status_code} (200=found disk state, 404=no state at all — both valid)")


# ------------------------------------------------------------------
# Runner
# ------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 60)
    print("API Integration Test — POST /chat + GET /state + crash reload")
    print(f"Backend: {BASE}")
    print(f"Session: {SESSION_ID}")
    print("=" * 60)

    # Verify server is up before running tests
    try:
        requests.get(f"{BASE}/", timeout=3)
    except Exception as e:
        print(f"\n[ERROR] Cannot reach {BASE}: {e}")
        print("Start the backend first:")
        print("  poetry run uvicorn src.api.main:app --reload --port 8000")
        sys.exit(1)

    tests = [
        test_health,
        test_chat_simple_message,
        test_chat_requirement_message,
        test_get_state_after_chat,
        test_crash_recovery_load_from_disk,
        test_chat_tool_use_message,
        test_session_continuity,
        test_chat_bad_request,
        test_get_state_unknown_session,
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
        print(f"All {len(tests)} API integration tests passed.")
    print("=" * 60)
