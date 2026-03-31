# Harness Roadmap

> This roadmap turns `PROJECT_HARNESS_PHILOSOPHY.md` into concrete implementation priorities.
>
> The goal is not to add agents as quickly as possible. The goal is to build a harness that lets agents perform software delivery work reliably, observably, and with human control at explicit boundaries.

---

# 1. Roadmap summary

The project should evolve in four phases:

1. **Phase 1 — Control plane stabilization**
   Make the current workflow semantically correct and testable.

2. **Phase 2 — Single-step execution loop**
   Make one approved step executable, verifiable, and recoverable.

3. **Phase 3 — Evidence and verification harness**
   Make agent work provable through structured validation outputs.

4. **Phase 4 — Knowledge and enforcement system**
   Make the repository itself a durable operating environment for agents.

The immediate next step is **Phase 1**, then **Phase 2**.

---

# 2. Guiding roadmap rule

At each stage, prioritize the work that most improves:

- correctness of structured state
- clarity of approval boundaries
- reliability of execution
- quality of verification
- recoverability after failure
- agent legibility of the repository

Do **not** prioritize new node count, prompt complexity, or demo breadth over harness quality.

---

# 3. Phase 1 — Control plane stabilization

## 3.1 Objective

Finish turning the current backend into a reliable control plane.

At the end of this phase, the system should have a clean and testable planning control flow where:

- state fields mean what the product says they mean
- approval boundaries are explicit
- retry behavior is explicit
- routing no longer depends on accidental node behavior
- frontend can trust structured state instead of inferring from messages

## 3.2 Why this phase matters

Without a stable control plane, later execution work will be built on ambiguous semantics.
That causes the system to feel agentic in demos but unreliable in practice.

## 3.3 Scope

### A. Finish product-state semantics
Continue aligning backend behavior with:
- `.claude/AGENT_FIRST_WORKFLOW_GUIDE.md`
- `.claude/BACKEND_STATE_SCHEMA_PROPOSAL.md`
- `.claude/PROJECT_HARNESS_PHILOSOPHY.md`

Focus on:
- `plan_status`
- `run_status`
- `approval_required`
- `approval_type`
- `approval_payload`
- `pending_approvals`
- `risk_actions`

### B. Make routing contracts explicit
Clarify the role of:
- `mode`
- `current_agent`
- `next_node`
- `trigger_plan`
- `interface_refresh`

The graph should route because the state is intentionally correct, not because one node happens to leave behind a lucky field combination.

### C. Define planning-phase node contracts
Document and enforce contracts for:
- `chat_node`
- `planner_node`
- `interface_node`
- `error_node`
- `central_coordinator`

Each contract should answer:
- when this node may run
- what state it reads
- what state it is allowed to change
- what success means
- what failure means
- when it must escalate to approval

### D. Strengthen tests around state transitions
Add or improve tests for:
- happy-path planning transitions
- retry transitions
- retry exhaustion transitions
- approval boundary transitions
- graph entry behavior
- no accidental chat execution in planning mode

## 3.4 Deliverables

By the end of Phase 1, the repo should contain:

- stable planning and error state transitions
- tests that cover the planning control loop
- a written node/state contract for current planning nodes
- fewer ambiguous meanings for `next_node` and `mode`

## 3.5 Exit criteria

Phase 1 is complete when:

- planning state transitions are testable and predictable
- retries and approvals are explicit in structured state
- graph entry and routing behavior are stable
- frontend can render the planning workflow from backend state alone

---

# 4. Phase 2 — Single-step execution loop

## 4.1 Objective

Build the smallest real execution loop.

The goal is not full multi-step autonomy yet.
The goal is to prove that the system can execute **one approved step** end-to-end with validation and recovery.

## 4.2 Why this phase matters

This is the first point where the project becomes more than a planning state machine.
A harness becomes real when the system can:
- do work
- evaluate its own work
- decide what to do next

## 4.3 Scope

### A. Introduce a minimal execution contract
Define what it means to execute one step.
A step run should minimally include:
- selected step id
- step intent
- implementation target
- action summary
- validation result
- execution outcome classification

### B. Implement one step runner path
A minimal path may look like:

1. plan is approved
2. system selects current pending step
3. agent produces or applies code changes for that step
4. system runs one validation command or verification routine
5. system classifies outcome into:
   - success
   - retry automatically
   - waiting approval
   - blocked
   - failed

### C. Add execution-visible state
The backend should clearly expose execution progress such as:
- current step id
- current step status
- current run status
- last validation summary
- last error summary
- retry metadata

### D. Add minimal approval handling for execution boundaries
Support structured approval for at least:
- execute plan
- retry after repeated execution failure
- risky command execution if required

## 4.4 Deliverables

By the end of Phase 2, the repo should contain:
- a documented single-step execution contract
- one real execution path from approved plan to validated step result
- structured outcome classification
- tests for single-step success and single-step failure escalation

## 4.5 Exit criteria

Phase 2 is complete when:
- the system can execute one approved step without relying on chat narration
- the system can validate the step result in a structured way
- the system can either continue, retry, block, or escalate based on evidence

---

# 5. Phase 3 — Evidence and verification harness

## 5.1 Objective

Turn validation from ad-hoc command output into a first-class evidence system.

## 5.2 Why this phase matters

If the harness cannot represent evidence well, then agent execution will remain opaque.
The system will know that something happened, but not whether the goal moved forward.

## 5.3 Scope

### A. Normalize validation outputs
Create structured schemas for things like:
- test results
- command results
- lint results
- build status
- runtime health checks
- step verification summaries

### B. Add failure classification
Teach the system to separate:
- retryable failures
- environment failures
- approval-boundary failures
- true terminal failures

### C. Connect evidence to runs and steps
Each step or run should be able to reference:
- what validation was performed
- what evidence was collected
- what failed
- what changed after retry

### D. Improve progress reporting
`progress_text` should remain useful for UX, but the deeper truth should live in structured fields.

## 5.4 Deliverables

By the end of Phase 3, the repo should contain:
- validation/evidence schemas
- normalized outcome types
- failure classification rules
- richer run/step summaries backed by evidence

## 5.5 Exit criteria

Phase 3 is complete when:
- the system can explain execution outcomes from structured evidence
- retries can be driven by evidence instead of generic failure text
- humans can inspect runs without reading raw logs first

---

# 6. Phase 4 — Knowledge and enforcement system

## 6.1 Objective

Turn the repository into a durable working environment for agents.

## 6.2 Why this phase matters

A harness does not scale if knowledge only lives in human memory or scattered notes.
To improve over time, the repository itself must become more legible and more enforceable.

## 6.3 Scope

### A. Build an indexed repo knowledge base
Gradually organize documentation into clear categories such as:
- philosophy
- architecture
- workflow/state contracts
- node contracts
- execution plans
- quality rules
- technical debt

### B. Use short entry docs, not giant manuals
Keep top-level guidance short and navigable.
Prefer maps and indexes over long instruction blobs.

### C. Encode rules mechanically
Turn important principles into:
- tests
- structural checks
- lint rules
- schema validation
- forbidden-pattern checks

### D. Add recurring cleanup and coherence work
Eventually the system should support recurring work such as:
- docs freshness checks
- stale design cleanup
- structural drift detection
- targeted refactor suggestions

## 6.4 Deliverables

By the end of Phase 4, the repo should contain:
- a clearer documentation structure
- explicit contract docs for core workflows
- some mechanically enforced harness principles
- a path toward ongoing coherence maintenance

## 6.5 Exit criteria

Phase 4 is complete when:
- agents can find the right repo knowledge without huge prompts
- core architectural and workflow invariants are enforced mechanically
- repository drift is easier to detect and correct

---

# 7. What should NOT happen yet

Until Phases 1 and 2 are solid, avoid prioritizing:

- many new node types
- broad multi-agent orchestration complexity
- long-lived autonomous runs without evidence contracts
- UI polish that papers over missing backend semantics
- prompt tuning as the main strategy for reliability

These may become useful later, but right now they can hide missing harness foundations.

---

# 8. Immediate next actions

The next concrete actions should be:

1. finish Phase 1 control-plane cleanup
2. write explicit contracts for current planning nodes and routing fields
3. define the minimal single-step execution state shape
4. define the single-step execution outcome categories
5. implement one narrow execution path with one verification path
6. add tests for success / retry / approval / blocked outcomes

---

# 9. Recommended short-term document set

To support the roadmap, the following docs would be useful next:

- `.claude/STATE_MACHINE_CONTRACT.md`
- `.claude/NODE_CONTRACTS.md`
- `.claude/SINGLE_STEP_EXECUTION_LOOP.md`
- `.claude/VALIDATION_EVIDENCE_SCHEMA.md`

These do not all need to be written immediately, but they are the right next documentation targets.

---

# 10. Final roadmap statement

The project should move from:

- a node graph that can plan

toward:

- a harness that can control, execute, validate, recover, and escalate correctly

That is the path from "agent prototype" to "agentic software delivery system."
