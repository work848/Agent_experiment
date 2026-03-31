# Backend Action Enforcement

## Session-scoped persistence is canonical truth

Every session's state is stored at:
```
src/memory/state/sessions/{session_id}.json
```

- Written by `save_session_state(state)` after every `/chat` call and approval resolution.
- Read by `load_session_state(AgentState, session_id)` at the start of every request.
- The in-process `conversations` dict is a performance cache only — it is not authoritative.
- `src/memory/state/current_state.json` is a legacy fallback (read-only, never written by the main path).

## Action flow

```
POST /chat
  ├─ approval_resolution present?
  │    └─ resolve_approval() → save_session_state() → return (skip graph)
  ├─ last_user_action present?
  │    ├─ evaluate_action() → AWAIT_EXISTING_GATE / REJECT → return {gated: true}
  │    └─ APPLY → handle_user_action() → (enter graph)
  └─ (enter graph) → save_session_state()
```

## Canonical truth fields

| Field | Meaning |
|-------|---------|
| `session_id` | Unique lifecycle identity for this conversation |
| `run_id` | Identity of the current execution run |
| `run_status` | Authoritative execution lifecycle state |
| `pending_approvals` | All approval requests with full lifecycle status |
| `action_gate` | Explicit gate blocking further actions |
| `approval_required` / `approval_type` / `approval_payload` | Compatibility projections derived from `pending_approvals` / `action_gate` |
| `risk_actions` | Risk events requiring review |

## Compatibility projections (not authoritative)

- `approval_required`, `approval_type`, `approval_payload` — kept for frontend compatibility; derived from `pending_approvals` and `action_gate`.
- `suggested_actions` — UI hints only; backend policy does not trust them as authorization.

## Policy rules (enforced in `src/utils/action_policy.py`)

1. If `action_gate.type != NONE` → `AWAIT_EXISTING_GATE`
2. If any `pending_approvals` entry has `status=PENDING` (and action is not gate-exempt) → `AWAIT_EXISTING_GATE`
3. If `run_status == WAITING_APPROVAL` (and action is not gate-exempt) → `AWAIT_EXISTING_GATE`
4. Otherwise → `APPLY`

Gate-exempt actions: `CONTINUE_CHAT`

## Tests that mechanically protect these invariants

| Test file | What it protects |
|-----------|------------------|
| `tests/test_action_policy.py` | Every `UserAction` evaluated against representative states; gate rules |
| `tests/test_state_persistence.py` | Session-scoped save/load round-trip; session isolation |
| `tests/test_approval_flow.py` | Approval approved/rejected lifecycle; gate cleared on approval |
| `tests/test_error_flow.py` | Execution → escalation → approval lifecycle end-to-end |

## Running tests

```bash
cd src
python ../tests/test_action_policy.py
python ../tests/test_state_persistence.py
python ../tests/test_approval_flow.py
```

For pytest-based tests (test_error_flow.py):
```bash
cd src && poetry run pytest ../tests/test_error_flow.py -v
```
