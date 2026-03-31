# Agent-First Workflow Guide

> Priority 0: backend design and implementation should follow this document before local optimizations, node-level convenience, or temporary API shortcuts.
>
> For concrete enums, AgentState fields, API response shape, and migration order, read `BACKEND_STATE_SCHEMA_PROPOSAL.md` together with this file.

## 1. Product philosophy

This system is **agent-first, human-controlled at boundaries**.

The goal is not to make humans review every code change. The goal is to let agents execute quickly while preserving human control over:

1. whether a generated plan should start executing
2. whether structural step changes / backtracking should be accepted
3. whether command execution should be allowed
4. whether repeated failures should escalate to a human retry decision

### What humans should NOT approve

Humans should **not** approve normal code writing work. If code generation becomes approval-heavy, the system stops being agent-first.

### What humans MUST approve

Humans must approve these boundary transitions:

- Execute a plan after plan generation
- Accept agent-proposed step changes, reordering, deletion, insertion, or backtracking
- Approve command execution / risky operations
- Approve retry after continuous failures or retry budget exhaustion

---

## 2. Core product objects

The product should be modeled around three first-class objects:

### Goal
Represents **what the user wants to achieve**.

Examples:
- integrate backend API
- redesign workspace UI
- fix execution retry logic

Goal answers: **why are we doing this?**

### Plan
Represents **the approved execution structure** for a goal.

A plan is a structured set of steps, dependencies, and ordering decisions.

Plan answers: **how do we intend to do it?**

### Run
Represents **one concrete execution instance of a plan**.

A single plan may have multiple runs.

Examples:
- Run #1 fails on step 3
- Run #2 resumes after human-approved step change
- Run #3 succeeds

Run answers: **what is happening right now during execution?**

---

## 3. State model

## 3.1 GoalStatus

Recommended enum:

```python
class GoalStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
```

Meaning:
- `pending`: goal exists but execution has not really started
- `in_progress`: plan or run activity exists for this goal
- `done`: user goal is achieved

Optional future extension:
- `abandoned`

---

## 3.2 PlanStatus

Plan status should describe the **readiness and lifecycle of the plan itself**, not whether code has already been written.

Recommended enum:

```python
class PlanStatus(str, Enum):
    DRAFT = "draft"
    READY = "ready"
    APPROVED = "approved"
    SUPERSEDED = "superseded"
```

Meaning:
- `draft`: plan is still being assembled or modified
- `ready`: plan is complete enough for human confirmation
- `approved`: human approved execution of this plan
- `superseded`: replaced by a newer plan version

Important:
- Step execution success/failure belongs to `StepStatus` / `RunStatus`
- It should not be overloaded into `PlanStatus`

---

## 3.3 StepStatus

Recommended enum:

```python
class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
```

This already matches the current backend direction and should remain execution-oriented.

---

## 3.4 RunStatus

Run is the most important execution-level state.

Recommended enum for first implementation:

```python
class RunStatus(str, Enum):
    IDLE = "idle"
    WAITING_APPROVAL = "waiting_approval"
    RUNNING = "running"
    BLOCKED = "blocked"
    FAILED = "failed"
    SUCCESS = "success"
```

Meaning:
- `idle`: plan exists, but execution has not started yet
- `waiting_approval`: run is paused at a human approval boundary
- `running`: agent execution is actively progressing
- `blocked`: run cannot continue because of an unresolved obstacle
- `failed`: run terminated unsuccessfully
- `success`: run completed successfully

Optional future extensions:
- `paused`
- `cancelled`

### Why `waiting_approval` matters

This is the key state for the product. It distinguishes:
- system failure
- system blockage
- intentional transfer of control back to the human

Without this state, the UI cannot cleanly express pending approvals.

---

## 4. Approval model

The backend should expose approval state explicitly rather than forcing the frontend to infer it from logs.

Recommended fields on execution state:

```python
approval_required: bool = False
approval_type: Optional[str] = None
approval_payload: Optional[dict] = None
```

Recommended approval types:

- `execute_plan`
- `step_change`
- `run_command`
- `retry_after_failure`

### approval_type meaning

- `execute_plan`: plan is ready, waiting for human to start a run
- `step_change`: agent proposes structural modification to steps or backtracking
- `run_command`: agent wants to execute a command or risky action
- `retry_after_failure`: retry budget or repeated failure threshold reached

### approval_payload

Should contain structured context, not only text.

Examples:
- affected step ids
- command preview
- reason for retry escalation
- proposed step diff summary
- risk level

The frontend workspace should render pending approvals from these fields directly.

---

## 5. Relationship between Goal / Plan / Run

The backend should keep these concerns separate:

- `Goal` tracks user intent and outcome
- `Plan` tracks execution design
- `Run` tracks active execution lifecycle

### Example

- Goal: add backend API integration
- Plan v1: 6 steps
- Run #1: blocked on command approval
- Run #2: failed after repeated retry exhaustion
- Run #3: success after human-approved step change

This separation is important because the same plan may be executed multiple times and the same goal may evolve across multiple plans.

---

## 6. Recommended run transitions

Primary lifecycle:

```text
idle -> waiting_approval   (plan generated, waiting for execute confirmation)
waiting_approval -> running
running -> waiting_approval   (step change / command approval / retry escalation)
running -> blocked
running -> failed
running -> success
blocked -> running
blocked -> waiting_approval
failed -> waiting_approval    (if system asks human whether to retry)
```

Guidance:
- human approval boundaries should produce `waiting_approval`
- technical obstacles should produce `blocked`
- terminal unsuccessful end should produce `failed`

---

## 7. Mapping to the current backend state

The current backend already has useful pieces:

- `mode`
- `plan`
- `current_step`
- `current_agent`
- `next_node`
- `success`
- `retry_count`
- `retrying_node`
- `last_error_message`
- `progress_text`

These are useful, but they do not yet fully express the product model.

### Current roles of existing fields

- `mode` is a coarse high-level machine mode (`chat / planning / executing`)
- `current_step` identifies where execution is
- `current_agent` / `next_node` show agent routing
- `success` indicates final success
- retry/error fields provide execution diagnostics

### What is still missing

To support the intended UX, backend state should explicitly expose:

```python
goal_status: GoalStatus
plan_status: PlanStatus
run_status: RunStatus
approval_required: bool
approval_type: Optional[str]
approval_payload: Optional[dict]
risk_actions: list[dict]
pending_approvals: list[dict]
```

At minimum, `run_status` + approval fields should be added first.

---

## 8. Workspace-first UI contract

The frontend workspace is the main work surface. Chat is auxiliary.

Therefore backend APIs should prioritize structured fields for workspace rendering over chat-only narration.

The workspace should be able to render these modules directly from backend state:

1. current goal
2. current plan status
3. current step status
4. agent status
5. risk actions
6. pending approvals

Chat should be used for:
- explanation
- clarification
- plan modification requests
- regenerate plan requests
- step-specific discussion

Goal / plan / current-step summary should live in structured workspace state, not only inside conversation text.

---

## 9. Backend implementation priorities

Recommended priority order:

### Priority 1
Add explicit execution state semantics:
- `run_status`
- `approval_required`
- `approval_type`
- `approval_payload`

### Priority 2
Separate coarse mode from product state:
- keep `mode` for internal routing if useful
- do not rely on `mode` alone as product state

### Priority 3
Expose workspace-oriented state in API responses:
- goal summary
- plan status
- run status
- pending approvals
- risk actions
- current step metadata

### Priority 4
Support multiple runs per plan when needed

---

## 10. Non-goals / anti-patterns

Do not design the backend around these assumptions:

- humans approve every code write
- chat transcript is the only source of truth
- plan status equals execution success
- retry escalation is only implied through logs
- command approval is hidden inside free-form assistant text

These patterns break the agent-first + human-boundary-control model.

---

## 11. Practical first-step schema recommendation

If only one backend change is made first, make it this:

```python
class RunStatus(str, Enum):
    IDLE = "idle"
    WAITING_APPROVAL = "waiting_approval"
    RUNNING = "running"
    BLOCKED = "blocked"
    FAILED = "failed"
    SUCCESS = "success"
```

and add to `AgentState`:

```python
run_status: RunStatus = RunStatus.IDLE
approval_required: bool = False
approval_type: Optional[str] = None
approval_payload: Optional[dict] = None
```

This unlocks the core product loop without requiring a full backend redesign.

---

## 12. Final rule

When backend implementation choices conflict with convenience, prefer the model that preserves:

- agent autonomy for normal execution
- human control at explicit boundaries
- structured workspace state over chat-only state
- separation of Goal / Plan / Run concerns

That is the core product direction.
