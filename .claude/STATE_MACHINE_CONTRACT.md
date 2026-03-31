# State Machine Contract

> Authoritative reference for all state transitions, routing rules, and valid state combinations.
> Derived from: `state.py`, `coordinator_node.py`, `user_action.py`, `approval_flow.py`, `action_policy.py`, `tester_node.py`.

---

## 1. Mode

```
CHAT ──[GENERATE_PLAN / REGENERATE_PLAN / MODIFY_PLAN]──► PLANNING
CHAT ──[GO_INTERFACE]──────────────────────────────────► PLANNING
PLANNING ──[EXECUTE_PLAN user action]──────────────────► EXECUTING
PLANNING ──[CONTINUE_CHAT]─────────────────────────────► CHAT
EXECUTING ──[resolve_approval(EXECUTE_PLAN)]───────────► EXECUTING  (mode set by resolve_approval)
any ──[CONTINUE_CHAT]──────────────────────────────────► CHAT
```

| Trigger | Owner | mode after |
|---------|-------|------------|
| `UserAction.GENERATE_PLAN` | `user_action.py` | `PLANNING` |
| `UserAction.REGENERATE_PLAN` | `user_action.py` | `PLANNING` |
| `UserAction.MODIFY_PLAN` | `user_action.py` | `PLANNING` |
| `UserAction.GO_INTERFACE` | `user_action.py` | `PLANNING` |
| `UserAction.EXECUTE_PLAN` | `user_action.py` | `EXECUTING` |
| `UserAction.CONTINUE_CHAT` | `user_action.py` | `CHAT` |
| `resolve_approval(EXECUTE_PLAN, APPROVED)` | `approval_flow.py` | `EXECUTING` |

---

## 2. PlanStatus

```
DRAFT ──[planner_node success]──────────────────────────► DRAFT (plan updated)
DRAFT ──[interface_node success]────────────────────────► READY
READY ──[UserAction.EXECUTE_PLAN]───────────────────────► APPROVED
READY ──[UserAction.REGENERATE_PLAN / MODIFY_PLAN]──────► DRAFT
APPROVED ──[UserAction.REGENERATE_PLAN / MODIFY_PLAN]───► DRAFT  (old plan superseded conceptually)
```

| Value | Meaning | Who writes it |
|-------|---------|---------------|
| `DRAFT` | Plan generated but not complete | `user_action.py` (GENERATE/REGENERATE/MODIFY) |
| `READY` | Interface complete; awaiting execute approval | `interface_node` (on success) |
| `APPROVED` | Human approved execution | `user_action.py` (EXECUTE_PLAN) |
| `SUPERSEDED` | A new plan replaced this one | Not yet written automatically; reserved for future |

---

## 3. RunStatus

```
IDLE
 │
 ├─[UserAction.EXECUTE_PLAN]────────────────────────────► RUNNING
 ├─[UserAction.GENERATE_PLAN / REGENERATE_PLAN]─────────► RUNNING  (transient during planning)
 │
RUNNING
 │
 ├─[tester: step success, more steps remain]────────────► RUNNING
 ├─[tester: all steps success]──────────────────────────► SUCCESS
 ├─[tester: retry budget exhausted]─────────────────────► WAITING_APPROVAL
 ├─[tester: file missing / invalid target]──────────────► BLOCKED
 ├─[coder: codegen failure]─────────────────────────────► FAILED
 │
WAITING_APPROVAL
 │
 ├─[resolve_approval(APPROVED)]─────────────────────────► RUNNING
 ├─[resolve_approval(REJECTED)]─────────────────────────► BLOCKED
 │
BLOCKED / FAILED / SUCCESS  ── terminal (coordinator routes to END)
```

| Value | Meaning | Who writes it |
|-------|---------|---------------|
| `IDLE` | No active run | `user_action.py` (CONTINUE_CHAT) |
| `RUNNING` | Execution active | `user_action.py` (EXECUTE_PLAN), `approval_flow.py` (APPROVED), `tester_node` (retry path) |
| `WAITING_APPROVAL` | Blocked at human boundary | `tester_node` (retry exhausted), `interface_node` (execute_plan gate) |
| `BLOCKED` | Environment/dependency obstacle | `tester_node` (BLOCKED paths), `approval_flow.py` (REJECTED) |
| `FAILED` | Terminal failure | `coder_node` (codegen error) |
| `SUCCESS` | All steps complete | `tester_node` (all steps success) |

---

## 4. Coordinator Routing (`central_coordinator`)

Evaluated in this priority order on every graph step:

| Priority | Condition | Routes to |
|----------|-----------|----------|
| 1 | `tool_call` is set | `current_agent` (re-enter same node) |
| 2 | Unresolved mail in `mailbox` | `mail.target` |
| 3 | `success == True` | `END` |
| 4 | `next_node == ERROR` | `error` |
| 5 | `last_user_action` set | apply action, then route to `next_node` |
| 6 | `mode == CHAT` | `chat` (or `END` if last message is assistant) |
| 7 | `mode == PLANNING`, `trigger_plan` | `planner` |
| 8 | `mode == PLANNING`, `interface_refresh` | `interface` |
| 9 | `mode == PLANNING`, `current_agent == planner` | `interface` |
| 10 | `mode == PLANNING`, `current_agent in {interface, error}` | `END` |
| 11 | `mode == EXECUTING`, `next_node == TESTER` | `tester` |
| 12 | `mode == EXECUTING`, `approval_required` | `END` |
| 13 | `mode == EXECUTING`, `run_status in {WAITING_APPROVAL, BLOCKED, FAILED, SUCCESS}` | `END` |
| 14 | `mode == EXECUTING`, `run_status == RUNNING` | `coder` |
| 15 | fallback | `END` |

---

## 5. UserAction → State Mutations

| UserAction | mode | plan_status | run_status | next_node | trigger_plan | interface_refresh |
|------------|------|-------------|------------|-----------|-------------|-------------------|
| `GENERATE_PLAN` | PLANNING | DRAFT | RUNNING | PLANNER | True | — |
| `REGENERATE_PLAN` | PLANNING | DRAFT | RUNNING | PLANNER | True | — |
| `MODIFY_PLAN` | PLANNING | DRAFT | RUNNING | PLANNER | True | — |
| `GO_INTERFACE` | PLANNING | — | RUNNING | INTERFACE | False | True |
| `EXECUTE_PLAN` | EXECUTING | APPROVED | RUNNING | None | False | False |
| `CONTINUE_CHAT` | CHAT | — | IDLE | CHAT | False | — |
| `SAVE_PLAN` | — | — | — | None | — | — |

All actions also clear: `approval_required = False`, `approval_type = None`, `approval_payload = None` (except SAVE_PLAN).

`EXECUTE_PLAN` additionally clears: `current_step_id`, `current_step_title`, `last_action_summary`, `last_validation_*`, `last_evidence`, `last_outcome`.

---

## 6. ApprovalRequest Lifecycle

```
PENDING
 ├─[resolve_approval(APPROVED)]──► APPROVED  + run_status=RUNNING, gate cleared
 │                                   └─ if type==EXECUTE_PLAN: mode=EXECUTING
 │                                   └─ if type==RETRY_AFTER_FAILURE: failed step reset to PENDING
 └─[resolve_approval(REJECTED)]──► REJECTED  + run_status=BLOCKED

EXPIRED / SUPERSEDED — reserved; not yet written automatically
```

| ApprovalType | Created by | Approved effect | Rejected effect |
|--------------|------------|-----------------|------------------|
| `EXECUTE_PLAN` | `interface_node` | mode→EXECUTING, run→RUNNING | run→BLOCKED |
| `RETRY_AFTER_FAILURE` | `tester_node` | failed step→PENDING, run→RUNNING | run→BLOCKED |
| `STEP_CHANGE` | reserved | run→RUNNING | run→BLOCKED |
| `RUN_COMMAND` | reserved | run→RUNNING | run→BLOCKED |

---

## 7. ActionGate Policy (`action_policy.py`)

Evaluated on every `POST /chat` that carries a `last_user_action`.

| Rule | Condition | Decision |
|------|-----------|----------|
| 1 | `action_gate.type != NONE` | `AWAIT_EXISTING_GATE` |
| 2 | any `pending_approvals` with `status=PENDING` (non-exempt action) | `AWAIT_EXISTING_GATE` |
| 3 | `run_status == WAITING_APPROVAL` (non-exempt action) | `AWAIT_EXISTING_GATE` |
| 4 | action unknown | `REJECT` |
| 5 | otherwise | `APPLY` |

**Gate-exempt actions:** `CONTINUE_CHAT`

---

## 8. StepStatus + StepOutcome → RunStatus Mapping

Produced by `tester_node` after each validation attempt:

| Condition | step.status after | StepOutcome | RunStatus |
|-----------|-------------------|-------------|----------|
| Validation passed, more steps pending | `SUCCESS` | `SUCCESS` | `RUNNING` |
| Validation passed, no more pending steps | `SUCCESS` | `SUCCESS` | `SUCCESS` |
| Validation failed, retries remaining | `PENDING` (reset) | `RETRY` | `RUNNING` |
| Validation failed, retry budget exhausted | `FAILED` | `WAITING_APPROVAL` | `WAITING_APPROVAL` |
| File missing / invalid target / no workspace | `FAILED` | `BLOCKED` | `BLOCKED` |

Retry budget: `MAX_STEP_RETRIES = 2` (defined in `tester_node.py`).

Coder failure (no valid code block extracted): `run_status=FAILED`, `StepOutcome=FAILED`, `step.status=FAILED`.

---

## 9. Forbidden State Combinations

These combinations should never occur in correct operation:

- `mode=EXECUTING` with `plan_status=DRAFT` — execution requires `APPROVED`
- `mode=EXECUTING` with `run_status=IDLE` — executing mode must have an active run
- `run_status=SUCCESS` with any step having `status=PENDING` or `FAILED` — success requires all steps done
- `run_status=RUNNING` with `approval_required=True` — running and waiting are mutually exclusive
- `approval_required=True` with empty `pending_approvals` — approval flag must have a backing request
- `mode=CHAT` with `trigger_plan=True` — planning trigger only valid in PLANNING mode
- `plan_status=APPROVED` with `mode=PLANNING` — approved plan should have transitioned to EXECUTING

---

## 10. Enum Quick Reference

| Enum | Values |
|------|--------|
| `Mode` | `chat`, `planning`, `executing` |
| `PlanStatus` | `draft`, `ready`, `approved`, `superseded` |
| `RunStatus` | `idle`, `waiting_approval`, `running`, `blocked`, `failed`, `success` |
| `StepStatus` | `pending`, `running`, `success`, `failed` |
| `StepOutcome` | `success`, `retry`, `waiting_approval`, `blocked`, `failed` |
| `ValidationStatus` | `passed`, `failed`, `blocked` |
| `FailureCategory` | `missing_implementation`, `missing_file`, `invalid_target`, `execution_error`, `unknown` |
| `ApprovalType` | `execute_plan`, `step_change`, `run_command`, `retry_after_failure` |
| `ApprovalStatus` | `pending`, `approved`, `rejected`, `expired`, `superseded` |
| `ActionGateType` | `none`, `approval_required`, `risk_review_required`, `awaiting_resolution` |
| `UserAction` | `save_plan`, `regenerate_plan`, `go_interface`, `generate_plan`, `continue_chat`, `modify_plan`, `execute_plan` |
| `NextNode` | `chat`, `planner`, `interface`, `coder`, `tester`, `error`, `END` |
