# Node Contracts

> This document defines node-level contracts for the harness.
>
> The goal is not to describe implementation details line by line. The goal is to define what each node is responsible for, what state it may read, what state it may write, and what conditions count as success, failure, retry, block, or approval escalation.

---

## 1. Why node contracts exist

In an agentic harness, nodes should not be understood as arbitrary code buckets.
Each node is a controlled state transition boundary.

A node contract exists to answer:

- when the node is allowed to run
- what state the node depends on
- what state the node may change
- what the node must not change
- what success means
- what failure means
- when the node must escalate to approval

If these rules are unclear, the graph may still run, but the harness will drift.

---

## 2. Global contract rules

These rules apply to all nodes unless explicitly stated otherwise.

## 2.1 Structured state first
Nodes must communicate product-relevant outcomes through structured state, not only through assistant message text.

## 2.2 Minimal writes
A node should only write fields that are part of its responsibility.
It should not opportunistically rewrite unrelated parts of state.

## 2.3 Explicit failure semantics
If a node fails, it should write enough structured information for the next control decision to be deterministic.

## 2.4 Approval is a control boundary
If a node reaches a condition that requires human judgment or authorization, it must expose that through approval fields instead of continuing implicitly.

## 2.5 Routing fields are not product-state substitutes
Fields like `mode`, `current_agent`, `next_node`, `trigger_plan`, and `interface_refresh` are control-plane fields.
They do not replace `plan_status`, `run_status`, `approval_*`, or future execution evidence fields.

## 2.6 No hidden side effects
A node should not silently:
- mutate plan structure without contract support
- advance execution through multiple semantic phases at once
- trigger risky operations without surfacing approval or risk state

---

## 3. Shared field roles

Before defining node contracts, the shared field categories should be explicit.

### 3.1 Intent / planning fields
- `requirements`
- `goal`
- `plan`
- `plan_status`
- `ready_for_plan`
- `suggested_actions`

### 3.2 Control / routing fields
- `mode`
- `current_agent`
- `next_node`
- `trigger_plan`
- `interface_refresh`
- `last_user_action`

### 3.3 Execution / run fields
- `current_step`
- `run_id`
- `run_status`
- `success`
- `retry_count`
- `retrying_node`
- `progress_text`
- future step-run summary fields

### 3.4 Failure / approval fields
- `last_failed_node`
- `last_error_message`
- `approval_required`
- `approval_type`
- `approval_payload`
- `pending_approvals`
- `risk_actions`

---

# 4. Current planning-phase node contracts

These are the contracts that should govern the current planning harness.

---

## 4.1 `chat_node`

### Purpose
Convert user conversation into clarified intent and planning readiness.

### Allowed to run when
- `mode == Mode.CHAT`

If `mode != Mode.CHAT`, `chat_node` should be a no-op and should not call chat LLM behavior.

### Reads
- `messages`
- `requirements`
- `ready_for_plan`
- `mode`

### May write
- `messages`
- `requirements`
- `ready_for_plan`
- `suggested_actions`
- `mode`
- `trigger_plan`
- `next_node`

### Must not directly own
- final planning approval state
- execution state transitions
- retry escalation semantics

### Success means
One of the following:
1. the conversation continues in chat mode with refined requirements, or
2. the system determines that planning should begin and sets the planning trigger fields

### Failure means
- requirement extraction or chat generation fails in a way that prevents useful continuation
- if failure is recoverable internally, the node may degrade gracefully
- it should not silently corrupt planning state

### Approval behavior
`chat_node` should not be the node that requests execution approval.
It may suggest planning, but the approval boundary for executing a plan belongs later in the flow.

---

## 4.2 `planner_node`

### Purpose
Generate a draft implementation plan from structured requirements.

### Allowed to run when
- `mode == Mode.PLANNING`
- `trigger_plan == True`

### Reads
- `requirements`
- `messages` only if needed for safe fallback context
- `plan` for preserving existing step data
- `workspace_root` only if planning context genuinely requires it

### May write
- `plan`
- `requirements` step mappings
- `current_step`
- `trigger_plan`
- `interface_refresh`
- `current_agent`
- `last_failed_node`
- `last_error_message`
- `retry_count`
- `retrying_node`
- `progress_text`
- `plan_status`
- `run_status`
- `approval_required`
- `approval_type`
- `approval_payload`
- `next_node` on explicit failure routing

### Must not directly own
- final execute-plan approval boundary
- execution-step mutation
- multi-step execution logic

### Success means
- a draft plan exists
- requirement-to-step mapping is coherent
- the system is ready to proceed to interface completion

### Product-state expectation on success
- `plan_status = draft`
- `run_status = idle`
- approval fields cleared

### Failure means
- the node cannot generate a valid plan
- the system records structured planner failure and hands off to error handling

### Approval behavior
Planner success should **not** request execute approval yet.
The plan is still incomplete until interface definition is done.

---

## 4.3 `interface_node`

### Purpose
Complete interface definitions for draft steps so the plan becomes execution-ready.

### Allowed to run when
- `mode == Mode.PLANNING`
- `interface_refresh == True`, or
- routing indicates planner just completed and interface completion should follow

### Reads
- `plan`
- `workspace_root`
- current step interface state

### May write
- `plan`
- `interface_refresh`
- `trigger_plan`
- `current_agent`
- `last_failed_node`
- `last_error_message`
- `retry_count`
- `retrying_node`
- `progress_text`
- `plan_status`
- `run_status`
- `approval_required`
- `approval_type`
- `approval_payload`
- `next_node` on explicit failure routing

### Must not directly own
- plan execution itself
- arbitrary plan restructuring
- command execution approval

### Success means
- each pending step that needs an interface has one
- the plan is complete enough to be considered execution-ready

### Product-state expectation on success
- `plan_status = ready`
- `run_status = waiting_approval`
- `approval_required = True`
- `approval_type = execute_plan`

### Failure means
- interface completion fails and the system cannot safely continue
- explicit structured failure is written and routed to error handling

### Approval behavior
`interface_node` is the current planning-phase node that exposes the execute-plan approval boundary.

---

## 4.4 `error_node`

### Purpose
Classify node-level planning failures into retry, terminal failure, or approval escalation.

### Allowed to run when
- `last_failed_node` is set, or
- `next_node == error`

### Reads
- `last_failed_node`
- `last_error_message`
- `retry_count`
- `max_node_retries`
- `mode`
- `messages`

### May write
- `current_agent`
- `mode`
- `trigger_plan`
- `interface_refresh`
- `next_node`
- `retry_count`
- `retrying_node`
- `progress_text`
- `messages`
- `run_status`
- `approval_required`
- `approval_type`
- `approval_payload`

### Must not directly own
- creating new plans
- changing approved intent
- hiding failure state to keep the graph moving

### Success means
One of two things:
1. the node produces a valid automatic retry transition, or
2. the node produces a valid human-approval escalation when retry budget is exhausted

### Retry behavior
When automatic retry is still allowed:
- `run_status = running`
- approval fields cleared
- routing must explicitly point back to the failed planning node

### Final escalation behavior
When retry budget is exhausted:
- `run_status = waiting_approval`
- `approval_required = True`
- `approval_type = retry_after_failure`
- `approval_payload` includes structured failure context

### Failure means
If `error_node` itself cannot classify the failure cleanly, the safe fallback is to stop advancing and expose a clear blocked or approval-required state rather than continuing blindly.

---

## 4.5 `central_coordinator`

### Purpose
Decide which node runs next based on current structured state.

### Allowed to run when
- after graph entry
- after node completion
- after a user action changes state

### Reads
- `tool_call`
- `mailbox`
- `success`
- `next_node`
- `last_user_action`
- `mode`
- `trigger_plan`
- `interface_refresh`
- `current_agent`
- relevant approval / run status context when later execution phases are added

### May write
- it may apply `handle_user_action(...)` effects to state
- it may clear `last_user_action`
- it may consume `next_node` for routing handoff semantics

### Must not directly own
- business logic generation
- plan content generation
- interface generation
- validation logic
- arbitrary mutation of execution evidence

### Success means
The coordinator returns the correct next routing target based on state semantics.

### Failure means
If the coordinator cannot determine a safe next step, it should prefer stopping or routing to a safe failure path instead of guessing.

### Important rule
The coordinator is a router, not a product-state author.
It should not become the primary place where plan/run meaning is invented.
Nodes should write semantic state; the coordinator should route based on it.

---

# 5. Phase 2 execution contracts

These contracts are forward-looking and should guide the first real execution loop implementation.

---

## 5.1 Step selector / execution coordinator

### Purpose
Select the next executable step from an approved plan and prepare the execution attempt.

### Allowed to run when
- `plan_status == approved`
- `run_status == running`
- there exists a pending step with satisfied dependencies

### Reads
- `plan`
- `current_step`
- future `current_step_id`
- dependency information
- run metadata

### May write
- selected step identity fields
- `current_step`
- future execution intent summary fields
- `progress_text`
- `current_agent`

### Must not directly own
- code editing
- validation execution
- final outcome classification

### Success means
- one step is intentionally selected
- execution intent is prepared
- the system is ready to hand off to implementation

---

## 5.2 Implementation worker

### Purpose
Perform the scoped code change for the selected step.

### Allowed to run when
- a step has already been selected
- execution intent exists
- the run is active

### Reads
- selected step info
- plan step metadata
- workspace context
- relevant codebase state

### May write
- code changes
- action summary fields
- current step status to `running` if not already set
- structured failure context if implementation itself cannot proceed

### Must not directly own
- final validation truth
- approval boundary decisions unless a risky action must be surfaced immediately
- cross-step planning changes

### Success means
- the intended change attempt has been made
- the system is ready for validation

### Failure means
- no useful implementation attempt could be made
- failure details are structured enough for classifier / error handling

---

## 5.3 Validation worker

### Purpose
Run the chosen validation path for the current step and normalize the result.

### Allowed to run when
- implementation attempt completed
- selected validation path is known

### Reads
- current step info
- validation contract / validation target
- workspace state

### May write
- validation summary fields
- validation pass/fail fields
- structured command/test output summaries
- `progress_text`

### Must not directly own
- plan mutation
- step selection
- approval boundary policy beyond reporting validation evidence

### Success means
- validation evidence is captured in a structured and legible way
- the system has enough information to classify the outcome

### Failure means
- validation itself could not be meaningfully performed
- the system records whether that is a blocker, a retryable issue, or an escalation candidate

---

## 5.4 Outcome classifier / execution error handler

### Purpose
Translate implementation + validation results into product-state transitions.

### Allowed to run when
- a step execution attempt has produced evidence or failure context

### Reads
- current step state
- validation result
- retry metadata
- approval policy context
- error summaries

### May write
- current step status
- `run_status`
- retry metadata
- `approval_required`
- `approval_type`
- `approval_payload`
- `last_error_message`
- `progress_text`
- future `last_outcome` fields

### Must not directly own
- generating a new plan
- selecting a different unrelated step without explicit contract support

### Success means
The outcome is classified as one of:
- success
- retry
- waiting approval
- blocked
- failed

and all corresponding state fields are updated consistently.

### Important rule
This node is where Phase 2 execution semantics become real.
It must classify outcomes from evidence, not from vague assistant text.

---

# 6. Contract-driven implementation order

When writing Phase 2 code, implement in this order:

1. stabilize current planning-node contracts in practice
2. add execution-visible state fields
3. implement step selector contract
4. implement implementation worker contract
5. implement validation worker contract
6. implement outcome classifier contract
7. add tests for scenario-level execution transitions

This keeps the harness grounded in contracts rather than node proliferation.

---

# 7. Final rule

When a future implementation choice conflicts with this document, prefer the design that makes node responsibilities:

- narrower
- more explicit
- more testable
- more observable
- less dependent on chat narration
- more consistent with structured control boundaries

That is the correct node-contract direction for this project.
