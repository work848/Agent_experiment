# Backend State Schema Proposal

> This document converts `AGENT_FIRST_WORKFLOW_GUIDE.md` into concrete backend data structures, enum definitions, response shapes, and migration order.

## 1. Purpose

This proposal is the implementation bridge between product philosophy and backend code.

Use this document when changing:
- `src/agent/state.py`
- `src/api/main.py`
- user action handlers
- graph routing
- retry / approval / command execution behavior

If there is a conflict between convenience and this proposal, prefer the model that preserves:
- agent autonomy during normal execution
- human approval at explicit control boundaries
- structured workspace state over chat-only narration
- separation of Goal / Plan / Run

---

## 2. Design principles

### 2.1 Keep existing fields where they still help

The current backend already has useful execution fields:
- `mode`
- `current_step`
- `current_agent`
- `next_node`
- `ready_for_plan`
- `last_failed_node`
- `last_error_message`
- `retry_count`
- `retrying_node`
- `progress_text`
- `suggested_actions`

These should not be removed immediately.

### 2.2 Add product-state fields instead of overloading technical fields

`mode` is not enough.

- `mode` is an internal routing state
- `run_status` is a product-visible execution state

Both may exist at the same time.

### 2.3 Frontend should not infer approvals from logs

Approval state must be explicit in structured fields.

---

## 3. Recommended enums

## 3.1 GoalStatus

```python
class GoalStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
```

Optional later:

```python
    ABANDONED = "abandoned"
```

### Guidance
- Start simple
- Do not add extra goal terminal states until product actually needs them

---

## 3.2 PlanStatus

Replace the meaning of the current plan lifecycle with a more product-correct one.

```python
class PlanStatus(str, Enum):
    DRAFT = "draft"
    READY = "ready"
    APPROVED = "approved"
    SUPERSEDED = "superseded"
```

### Migration note

Current backend has:

```python
class PlanStatus(str, Enum):
    DRAFT = "draft"
    CONFIRM = "confirm"
    RUNNING = "running"
```

Recommended mapping during migration:
- `draft` -> `draft`
- `confirm` -> `ready`
- `running` -> `approved`

Reason:
- `running` is execution language, which belongs more naturally to `RunStatus`
- once a plan is being executed, the plan itself is best interpreted as `approved`

---

## 3.3 StepStatus

Keep as-is:

```python
class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
```

### Guidance
- This remains execution-oriented
- Do not rename `success` to `done` in backend internal models
- If frontend wants `done`, normalize at API boundary only

---

## 3.4 RunStatus

Add this as a new first-class enum.

```python
class RunStatus(str, Enum):
    IDLE = "idle"
    WAITING_APPROVAL = "waiting_approval"
    RUNNING = "running"
    BLOCKED = "blocked"
    FAILED = "failed"
    SUCCESS = "success"
```

Optional later:

```python
    PAUSED = "paused"
    CANCELLED = "cancelled"
```

### Meaning
- `idle`: plan exists but run has not started yet
- `waiting_approval`: run is waiting at a human boundary
- `running`: execution is active
- `blocked`: technical or dependency obstacle prevents progress
- `failed`: run ended unsuccessfully
- `success`: run completed successfully

### Important rule

When a human decision is required, prefer:
- `run_status = waiting_approval`

When the system cannot continue because of environment / dependency / infrastructure reasons, prefer:
- `run_status = blocked`

---

## 3.5 ApprovalType

Add a dedicated enum instead of raw strings spread across code.

```python
class ApprovalType(str, Enum):
    EXECUTE_PLAN = "execute_plan"
    STEP_CHANGE = "step_change"
    RUN_COMMAND = "run_command"
    RETRY_AFTER_FAILURE = "retry_after_failure"
```

### Meaning
- `execute_plan`: generated plan is ready; waiting for human to start execution
- `step_change`: agent proposes structural step edits, reorder, insertion, deletion, or backtracking
- `run_command`: agent wants to execute a command or risky operation
- `retry_after_failure`: repeated failure threshold reached; human must decide whether to continue

---

## 3.6 RiskActionType

Recommended if backend wants structured risk lists for workspace rendering.

```python
class RiskActionType(str, Enum):
    COMMAND = "command"
    FILE_WRITE = "file_write"
    PLAN_MUTATION = "plan_mutation"
    RETRY_ESCALATION = "retry_escalation"
```

This can be added later if needed. Not required for first migration.

---

## 4. Recommended data models

## 4.1 Goal

There is no first-class Goal model in the current backend. Add one in a minimal form.

```python
class Goal(BaseModel):
    id: str
    title: str
    description: str = ""
    status: GoalStatus = GoalStatus.PENDING
    success_criteria: List[str] = Field(default_factory=list)
```

### Guidance
- Keep it lightweight at first
- `title` is usually enough for UI summary
- `success_criteria` can remain optional and sparse

---

## 4.2 ApprovalRequest

```python
class ApprovalRequest(BaseModel):
    id: str
    type: ApprovalType
    title: str
    description: str
    created_at: Optional[str] = None
    step_id: Optional[str] = None
    blocking: bool = True
    payload: Dict[str, Any] = Field(default_factory=dict)
```

### Why a dedicated model

This is better than only using:
- `approval_required`
- `approval_type`
- `approval_payload`

because the workspace wants a list of pending approvals, not only a single flag.

### First-step compatibility

If the backend wants a smaller first version, it may start with:

```python
approval_required: bool = False
approval_type: Optional[ApprovalType] = None
approval_payload: Optional[dict] = None
```

and evolve later into:

```python
pending_approvals: List[ApprovalRequest] = Field(default_factory=list)
```

---

## 4.3 RiskAction

```python
class RiskAction(BaseModel):
    id: str
    type: str
    title: str
    description: str
    step_id: Optional[str] = None
    status: str = "pending"
    payload: Dict[str, Any] = Field(default_factory=dict)
```

### Guidance
- This is for workspace visibility
- Not every risk action must require immediate approval
- Some risks are informative; some are blocking

---

## 4.4 RunSummary

If a separate persistent Run model is too much initially, at least define a structured run view.

```python
class RunSummary(BaseModel):
    id: str
    status: RunStatus = RunStatus.IDLE
    current_step_id: Optional[str] = None
    current_step_index: int = 0
    current_agent: Optional[str] = None
    retry_count: int = 0
    retrying_node: Optional[str] = None
    last_error_message: Optional[str] = None
    progress_text: Optional[str] = None
```

### Guidance
- This can live inside `AgentState` first
- Later it can become a first-class persistent entity if multi-run history is needed

---

## 5. Recommended AgentState shape

The current `AgentState` should be extended, not rewritten from scratch.

## 5.1 Current important fields to retain

Retain these fields:

```python
session_id: str
messages: List[Dict]
workspace_root: Optional[str]
plan: Optional[List[Step]]
requirements: List[Requirement]
current_step: int
mailbox: List[Email]
current_agent: NextNode
next_node: NextNode
last_user_action: Optional[UserAction]
mode: Mode
ready_for_plan: bool
suggested_actions: List[Dict]
last_failed_node: Optional[NextNode]
last_error_message: Optional[str]
retry_count: int
max_node_retries: int
retrying_node: Optional[str]
progress_text: Optional[str]
success: bool
```

## 5.2 New fields to add now

Recommended first addition:

```python
goal: Optional[Goal] = None
plan_status: PlanStatus = PlanStatus.DRAFT
run_id: Optional[str] = None
run_status: RunStatus = RunStatus.IDLE
approval_required: bool = False
approval_type: Optional[ApprovalType] = None
approval_payload: Optional[Dict[str, Any]] = None
pending_approvals: List[ApprovalRequest] = Field(default_factory=list)
risk_actions: List[RiskAction] = Field(default_factory=list)
```

### Minimal version if the team wants lower migration cost

If the team wants the smallest safe first step, add only:

```python
plan_status: PlanStatus = PlanStatus.DRAFT
run_status: RunStatus = RunStatus.IDLE
approval_required: bool = False
approval_type: Optional[ApprovalType] = None
approval_payload: Optional[Dict[str, Any]] = None
```

This is the minimum schema that aligns the backend with the agreed workflow.

---

## 6. State derivation rules

These rules help keep state consistent during migration.

## 6.1 Deriving `plan_status`

Recommended rules:

- no plan or incomplete plan generation -> `draft`
- plan generated and awaiting human execute decision -> `ready`
- human approved execution for current plan -> `approved`
- a new plan replaces previous plan -> old plan becomes `superseded`

### Important

Do not set `plan_status = running` in the new model.
Running belongs to `run_status`.

---

## 6.2 Deriving `run_status`

Recommended rules:

### `idle`
Use when:
- plan exists
- execution has not started
- no blocking approval is active

### `waiting_approval`
Use when:
- `approval_required == True`
- or `pending_approvals` is non-empty and blocking

### `running`
Use when:
- graph is actively executing
- a step is in progress
- there is no blocking approval

### `blocked`
Use when:
- unresolved infrastructure / environment / dependency issue exists
- execution cannot continue automatically
- issue is not merely “waiting for human approval”

### `failed`
Use when:
- execution terminates unsuccessfully
- retry budget exhausted without entering approval continuation flow
- unrecoverable step failure happens

### `success`
Use when:
- all required execution work for this run finishes successfully
- current success semantics in backend are satisfied

---

## 6.3 `success` field migration guidance

Current backend uses:

```python
success: bool = False
```

Recommendation:
- keep `success` temporarily for backward compatibility
- make `run_status` the authoritative product field

Suggested compatibility rule:
- `success = (run_status == RunStatus.SUCCESS)`

Long term, `success` can become derived or be removed.

---

## 7. API response proposal

## 7.1 Current `/state` and `/chat` response gaps

Current response shape includes:
- plan
- requirements
- current_step
- agents
- logs
- messages
- ready_for_plan
- actions
- last_error_message
- retry_count
- retrying_node
- progress_text

Missing product-level fields:
- goal
- plan_status
- run_status
- approval state
- pending approvals
- risk actions

---

## 7.2 Proposed response shape

Recommended shape for both `GET /state` and `POST /chat` responses:

```python
{
    "goal": {
        "id": "goal-001",
        "title": "Integrate backend API",
        "description": "",
        "status": "in_progress",
        "success_criteria": []
    },
    "plan": [...],
    "plan_status": "ready",
    "run": {
        "id": "run-001",
        "status": "waiting_approval",
        "current_step_id": "STEP-001",
        "current_step_index": 1,
        "current_agent": "planner",
        "retry_count": 0,
        "retrying_node": null,
        "last_error_message": null,
        "progress_text": "Plan generated. Waiting for approval."
    },
    "requirements": [...],
    "agents": {
        "planner": "idle",
        "coder": "idle",
        "tester": "idle"
    },
    "logs": [...],
    "messages": [...],
    "ready_for_plan": true,
    "actions": [...],
    "approval_required": true,
    "approval_type": "execute_plan",
    "approval_payload": {
        "plan_version": 1
    },
    "pending_approvals": [...],
    "risk_actions": [...],
    "last_error_message": null,
    "retry_count": 0,
    "retrying_node": null,
    "progress_text": "Plan generated. Waiting for approval."
}
```

### Response guidance

- Keep old fields temporarily if frontend depends on them
- Add new structured fields rather than replacing everything at once
- `run` object is cleaner than scattering run state across top-level fields only

---

## 7.3 Backward-compatible transitional shape

If a nested `run` object is too disruptive right now, return both:

```python
"plan_status": "ready",
"run_status": "waiting_approval",
"approval_required": true,
"approval_type": "execute_plan",
"approval_payload": {...},
"pending_approvals": [...],
"risk_actions": [...],
```

and keep old fields:

```python
"current_step": 1,
"retry_count": 0,
"retrying_node": null,
"progress_text": "...",
```

This is likely the safest first backend iteration.

---

## 8. Suggested action alignment

Current backend already exposes `suggested_actions`.

Recommended rule:
- actions are UI affordances
- approvals are state facts

Do not use `suggested_actions` as the only representation of pending approvals.

### Example

Good:
- `approval_required = true`
- `approval_type = "run_command"`
- `pending_approvals = [...]`
- `suggested_actions = [{"action": "approve_command", "label": "Approve command"}]`

Bad:
- only `suggested_actions` exists, but no explicit approval state exists

---

## 9. Migration plan

## Phase 1: add explicit fields without breaking current API

In `src/agent/state.py`:
- add `RunStatus`
- add `ApprovalType`
- extend `AgentState` with:
  - `plan_status`
  - `run_status`
  - `approval_required`
  - `approval_type`
  - `approval_payload`

In `src/api/main.py`:
- include these fields in `_build_state_response`
- persist them in session memory
- persist them in `save_state(...)`

This phase should not require frontend rewrites if responses remain additive.

## Phase 2: add list-based approval and risk models

Add:
- `ApprovalRequest`
- `RiskAction`
- `pending_approvals`
- `risk_actions`

This unlocks workspace modules cleanly.

## Phase 3: add first-class Goal object

Add:
- `Goal`
- `goal_status`
- goal summary in API

## Phase 4: consider first-class Run persistence

Only do this if product needs:
- run history
- multiple resumable runs per plan
- run analytics / auditability

---

## 10. Concrete file-by-file guidance

## `src/agent/state.py`

Recommended additions first:

1. add `GoalStatus`
2. replace/expand `PlanStatus`
3. add `RunStatus`
4. add `ApprovalType`
5. add `Goal`, `ApprovalRequest`, `RiskAction` models
6. extend `AgentState`

### Do not do yet
- full DB model split
- complicated historical run archive model
- extra enums for every edge case

Keep the first pass lean.

---

## `src/api/main.py`

Update these areas:

### `_build_state_response`
Must include:
- `plan_status`
- `run_status`
- `approval_required`
- `approval_type`
- `approval_payload`
- later: `pending_approvals`, `risk_actions`, `goal`

### `_session_to_state`
Must reconstruct the new fields from session memory.

### session default object in `/chat`
Must store the new fields.

### response payload from `/chat`
Must return the new fields.

### `save_state(...)`
Must persist the new fields.

---

## 11. Product-behavior examples

## Example A: plan generated, waiting to execute

Expected state:

```python
plan_status = PlanStatus.READY
run_status = RunStatus.WAITING_APPROVAL
approval_required = True
approval_type = ApprovalType.EXECUTE_PLAN
progress_text = "Plan generated. Waiting for approval to execute."
```

## Example B: agent asks to change steps

Expected state:

```python
run_status = RunStatus.WAITING_APPROVAL
approval_required = True
approval_type = ApprovalType.STEP_CHANGE
approval_payload = {
    "affected_step_ids": ["STEP-003", "STEP-004"],
    "reason": "Need to insert prerequisite migration step"
}
```

## Example C: command needs approval

Expected state:

```python
run_status = RunStatus.WAITING_APPROVAL
approval_required = True
approval_type = ApprovalType.RUN_COMMAND
approval_payload = {
    "command": "npm install",
    "working_directory": "/workspace/app"
}
```

## Example D: repeated failure escalation

Expected state:

```python
run_status = RunStatus.WAITING_APPROVAL
approval_required = True
approval_type = ApprovalType.RETRY_AFTER_FAILURE
retry_count = 2
last_error_message = "Interface generation failed twice"
```

## Example E: technical blockage without human decision yet

Expected state:

```python
run_status = RunStatus.BLOCKED
approval_required = False
approval_type = None
last_error_message = "workspace_root not found"
```

---

## 12. Final recommendation

If only one concrete backend schema change is adopted immediately, adopt this minimum set:

```python
class RunStatus(str, Enum):
    IDLE = "idle"
    WAITING_APPROVAL = "waiting_approval"
    RUNNING = "running"
    BLOCKED = "blocked"
    FAILED = "failed"
    SUCCESS = "success"

class ApprovalType(str, Enum):
    EXECUTE_PLAN = "execute_plan"
    STEP_CHANGE = "step_change"
    RUN_COMMAND = "run_command"
    RETRY_AFTER_FAILURE = "retry_after_failure"
```

and extend `AgentState` with:

```python
plan_status: PlanStatus = PlanStatus.DRAFT
run_status: RunStatus = RunStatus.IDLE
approval_required: bool = False
approval_type: Optional[ApprovalType] = None
approval_payload: Optional[Dict[str, Any]] = None
```

This is the smallest change that keeps the backend aligned with the agreed product direction.
