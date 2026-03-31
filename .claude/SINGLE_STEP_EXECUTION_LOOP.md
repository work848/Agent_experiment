# Single-Step Execution Loop

> This document defines **Phase 2** of `HARNESS_ROADMAP.md`.
>
> The purpose of Phase 2 is to prove that the harness can execute **one approved plan step** end-to-end with structured validation, failure classification, and explicit control-boundary escalation.

---

## 1. Objective

Phase 2 is the first point where the project stops being only a planning control system and becomes a real execution harness.

The objective is simple:

**Given an approved plan, the system should be able to execute one step, validate whether that execution advanced the goal, classify the result, and update structured state accordingly.**

This phase does **not** aim to solve:
- full multi-step autonomous delivery
- parallel step execution
- long-running background runs across many steps
- advanced UI automation
- generalized multi-agent self-review loops

Those may come later.

Phase 2 is about the smallest reliable execution loop.

---

## 2. Why single-step first

The project should not jump directly from planning into broad autonomous execution.

A harness becomes trustworthy when it can do one small unit of work well:

1. choose a step intentionally
2. execute it in a controlled way
3. validate the result
4. determine the correct next state
5. recover or escalate when needed

If this loop is weak, adding more nodes or more autonomy only increases failure surface area.

If this loop is strong, future autonomy compounds safely.

---

## 3. What counts as a "step" in Phase 2

A Phase 2 execution step is:

- a plan step that is already part of an approved plan
- still pending
- small enough to be attempted in one bounded execution cycle
- associated with a concrete implementation target or intended outcome
- paired with at least one validation path

A good Phase 2 step looks like:
- implement one function
- wire one API endpoint
- add one UI component behavior
- fix one scoped bug
- add one test-backed internal helper

A bad Phase 2 step looks like:
- refactor the entire subsystem
- build the whole frontend
- redesign architecture broadly
- perform many unrelated edits in one step

Phase 2 assumes step granularity is narrow enough to make validation meaningful.

---

## 4. Core loop definition

The single-step execution loop should follow this sequence:

1. **Plan approved**
2. **Select one pending step**
3. **Prepare execution intent**
4. **Perform implementation action**
5. **Run validation**
6. **Classify outcome**
7. **Write structured state**
8. **Decide next control transition**

This sequence is the minimum harness loop.

---

## 5. Phase 2 state model additions

Phase 2 should avoid overbuilding persistent models, but it needs enough structure to represent step execution cleanly.

## 5.1 Existing state to reuse

Use existing fields where possible:
- `plan`
- `current_step`
- `current_agent`
- `mode`
- `plan_status`
- `run_status`
- `approval_required`
- `approval_type`
- `approval_payload`
- `retry_count`
- `retrying_node`
- `last_error_message`
- `progress_text`

## 5.2 Recommended new execution-visible fields

Phase 2 should add a minimal structured execution layer, either directly on `AgentState` or as nested models later.

Recommended fields:

```python
current_step_id: Optional[str] = None
current_step_title: Optional[str] = None
last_action_summary: Optional[str] = None
last_validation_summary: Optional[str] = None
last_validation_passed: Optional[bool] = None
last_outcome: Optional[str] = None
```

If the team prefers stronger structure, this can instead be captured in a dedicated `StepRunSummary` model.

## 5.3 Recommended outcome enum

Phase 2 should introduce an explicit execution outcome classification.

```python
class StepOutcome(str, Enum):
    SUCCESS = "success"
    RETRY = "retry"
    WAITING_APPROVAL = "waiting_approval"
    BLOCKED = "blocked"
    FAILED = "failed"
```

### Meaning
- `success`: the step was completed and validation passed
- `retry`: the step did not succeed, but the system should automatically try again
- `waiting_approval`: human decision is required before continuing
- `blocked`: progress is prevented by an unresolved obstacle
- `failed`: this step attempt ended unsuccessfully and should not continue automatically

This outcome is not the same as `run_status`, but it helps derive it.

---

## 6. Step selection contract

Phase 2 should use a very simple step-selection rule.

### Rule
Select the first step in the approved plan whose status is `pending` and whose dependencies are already satisfied.

### Dependency satisfied means
A dependency is satisfied when the referenced step exists and has status `success`.

### Non-goals for Phase 2
Do **not** add:
- smart prioritization
- dynamic reordering
- parallel execution scheduling
- step insertion/deletion during execution

Those belong to later phases.

The point of Phase 2 is reliability, not scheduling sophistication.

---

## 7. Execution intent contract

Before code is changed, the system should form a lightweight execution intent for the selected step.

The intent should answer:
- what step is being executed
- what outcome is expected
- what files or surfaces are likely involved
- what validation will be used to judge success

This intent may be stored as structured fields or summarized in a single field like `last_action_summary`.

Example:

```text
Step: R001-S01
Intent: add login API handler in src/api/auth.py and validate with the auth unit test target.
```

The purpose of execution intent is not ceremony.
It is to make the action legible before validation happens.

---

## 8. Implementation action contract

The implementation part of Phase 2 should stay narrow.

### Allowed pattern
A single step execution may:
- inspect relevant code
- edit relevant code
- create small missing code files if absolutely necessary
- run bounded validation commands

### Disallowed pattern for Phase 2
A single step execution should not:
- mutate the plan structure
- jump across unrelated steps
- run open-ended shell workflows with unclear purpose
- continue indefinitely without validation
- silently perform risky operations that should be approvals

### Important rule
Implementation is not considered complete until validation has run.

---

## 9. Validation contract

Each Phase 2 step must have at least one validation method.

The validation method may be one of:
- a targeted test command
- a build or lint command
- a deterministic script
- a narrow runtime check
- a file-level structural assertion

### Validation requirements
A validation path should be:
- narrow
- attributable to the step
- reproducible
- understandable by both human and agent

### Phase 2 preference
Prefer the smallest validation that can prove useful progress.
Do not require a full-system validation for every step unless the step genuinely demands it.

---

## 10. Outcome classification rules

After validation, the system must classify the result.

## 10.1 SUCCESS
Use `success` when:
- implementation completed
- validation passed
- no approval boundary was triggered

State implications:
- current step status -> `success`
- `run_status` remains `running` if more steps remain, or may move later depending on run design
- approval fields cleared

## 10.2 RETRY
Use `retry` when:
- the step failed in a way that seems locally recoverable
- another bounded attempt is reasonable
- no human decision is yet required

Examples:
- generated code failed a test in a clearly fixable way
- formatting/lint issue produced an actionable error
- import or symbol mismatch from the same step edit

State implications:
- current step status stays `running` or returns to `pending` depending on implementation strategy
- `run_status = running`
- retry metadata updates
- no approval required yet

## 10.3 WAITING_APPROVAL
Use `waiting_approval` when:
- a risky command or boundary action must be approved
- repeated failures reached the escalation threshold
- the system wants to make a structural step change

State implications:
- `run_status = waiting_approval`
- `approval_required = True`
- `approval_type` populated
- `approval_payload` populated with structured context

## 10.4 BLOCKED
Use `blocked` when:
- progress cannot continue due to missing prerequisites or environment problems
- the system cannot safely fix the problem on its own
- a human may need to intervene, but the immediate situation is obstacle-first, not judgment-first

Examples:
- dependency unavailable
- workspace setup broken
- required file or service missing
- unresolved external integration issue

State implications:
- `run_status = blocked`
- approval may or may not be required depending on policy
- `last_error_message` and validation summary should clearly describe the blocker

## 10.5 FAILED
Use `failed` when:
- the step attempt has conclusively ended unsuccessfully
- automatic retries are exhausted and no retry escalation path is being taken in this exact transition
- continuing automatically would be wrong

In many product flows, `failed` will often be followed by `waiting_approval` once the system asks the human whether to retry. But the conceptual outcome should still remain distinct.

---

## 11. Control-boundary decisions in Phase 2

Phase 2 should support only a small number of execution-time approval boundaries.

## 11.1 Execute plan
Already part of Phase 1 semantics.
The plan must be approved before step execution begins.

## 11.2 Retry after repeated execution failure
If the step keeps failing and the retry budget is exhausted, the system should stop automatic progress and request human input.

Recommended approval payload:

```python
{
    "step_id": "R001-S01",
    "reason": "retry_budget_exhausted",
    "retry_count": 2,
    "max_retries": 2,
    "last_validation_summary": "Targeted auth validation still failing with import error"
}
```

## 11.3 Risky command approval
If the execution path requires a command that should not be run automatically, the system should escalate before executing it.

Examples:
- destructive filesystem operations
- shared-environment mutations
- database-destructive commands
- commands that exceed the harness's safe default scope

Phase 2 does not need a perfect risk engine. It only needs a clear place where such actions can stop and wait.

---

## 12. Proposed minimal node responsibilities for Phase 2

Phase 2 should avoid exploding node count.
A minimal execution flow can still be modeled with a few focused responsibilities.

Possible responsibility split:

### A. Step selector / execution coordinator
- selects current step
- prepares execution intent
- routes into implementation

### B. Implementation worker
- performs the scoped code change for the current step
- records an action summary

### C. Validation worker
- runs the defined validation path
- normalizes the result into structured fields

### D. Outcome / error classifier
- decides success vs retry vs blocked vs waiting approval vs failed
- updates product state

This may be implemented as several nodes or a smaller number of nodes internally. The key is the contract, not the node count.

---

## 13. State transition sketch

A minimal single-step Phase 2 lifecycle may look like this:

```text
plan_status=approved
run_status=running
step.status=pending

-> select step
-> step.status=running
-> implementation attempt
-> validation attempt

if validation passes:
    step.status=success
    outcome=success

if recoverable failure:
    outcome=retry
    run_status=running

if retry budget exhausted:
    outcome=waiting_approval
    run_status=waiting_approval
    approval_type=retry_after_failure

if environment blocker:
    outcome=blocked
    run_status=blocked

if conclusive terminal failure:
    outcome=failed
    run_status=failed
```

This sketch is intentionally small. It is enough to support real execution semantics.

---

## 14. Minimum test scenarios for Phase 2

Phase 2 should not be considered done without scenario-level tests.

Minimum scenarios:

1. **Single-step success**
   - approved plan exists
   - one pending step is selected
   - implementation succeeds
   - validation passes
   - step becomes success

2. **Single-step recoverable retry**
   - first implementation attempt fails validation
   - system classifies as retry
   - second attempt succeeds

3. **Retry exhaustion to approval**
   - repeated failure reaches retry limit
   - system enters `waiting_approval`
   - approval fields are populated

4. **Blocked environment case**
   - validation or setup indicates missing prerequisite
   - system enters `blocked`
   - error summary is structured and legible

5. **Risky command approval case**
   - execution wants to run a risky command
   - system pauses before running it
   - approval boundary is exposed in structured state

These tests are more important than broad end-to-end ambition.

---

## 15. What Phase 2 intentionally leaves for later

Phase 2 does not need to solve:
- multiple runs per plan history
- branch-per-step workflows
- multi-step planning adaptation during execution
- multi-agent debate/review
- UI/browser automation as a default execution primitive
- observability-backed runtime diagnosis
- autonomous PR creation and merge

Those belong to later harness phases after the single-step loop is trustworthy.

---

## 16. Recommended implementation order

The recommended implementation order for Phase 2 is:

1. define the minimal execution state additions
2. define the `StepOutcome` classification
3. define the step-selection rule
4. define the validation contract
5. implement one narrow implementation + validation path
6. wire retry / blocked / approval transitions
7. add scenario tests for the five minimum cases

This order keeps the project focused on harness correctness instead of feature sprawl.

---

## 17. Success criteria for Phase 2

Phase 2 is successful when all of the following are true:

- one approved step can be executed end-to-end
- validation is part of the loop, not an afterthought
- outcomes are classified explicitly
- state transitions are visible through structured backend fields
- retry and approval behavior are distinguishable
- the system can stop cleanly when judgment is required

If those are true, the project has crossed the line from planning prototype to real execution harness.

---

## 18. Final rule

When implementation choices conflict during Phase 2, prefer the design that makes a single-step run:

- more observable
- more classifiable
- more recoverable
- more testable
- more legible to future agents

That is the correct Phase 2 direction.
