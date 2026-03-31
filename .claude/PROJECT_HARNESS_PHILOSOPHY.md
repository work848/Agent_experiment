# Project Harness Philosophy

> This project is not primarily a "coding agent" project. It is a **harness engineering** project for agentic software delivery.
>
> The goal is to build an environment, control system, and feedback loop that lets agents do real software work reliably, while humans stay in control at explicit boundaries.

## 1. What this project is

This project is an **agent-first, human-at-boundaries software delivery harness**.

It exists to answer one question:

**How do we make agents reliably build, validate, repair, and ship software inside a controlled engineering system?**

The core unit of value is not "the model wrote code".
The core unit of value is:

- the agent could understand the task
- the agent could operate inside a structured environment
- the agent could verify whether progress was real
- the system knew when to continue, when to retry, and when to hand control back to a human

In other words:

- Humans steer
- Agents execute
- The harness makes that collaboration reliable

---

## 2. What this project is NOT

This project is **not** mainly trying to build:

- a chat-first coding bot
- a collection of agent nodes for their own sake
- a system where humans approve every code-writing step
- a workflow that depends on reading chat logs to infer real state
- a thin wrapper around prompt engineering

If the system only becomes better by adding more prompts or more nodes, but not by improving environment legibility, state contracts, and verification loops, then the project is drifting away from its real purpose.

---

## 3. Core belief: harness engineering over prompt engineering

Prompting matters, but prompt quality is not the main leverage point.

The main leverage point is the harness:

1. what the agent can see
2. what the agent is allowed to do
3. what the agent must prove before moving forward
4. what structured state the system records
5. what feedback loops exist after actions are taken
6. where humans must explicitly approve control-boundary transitions

A stronger harness is more valuable than a smarter single prompt.

---

## 4. The operating model

This project follows a simple operating model:

### 4.1 Humans define intent
Humans provide:
- goals
- constraints
- approval decisions
- quality expectations
- architectural judgment when tradeoffs matter

### 4.2 Agents do normal execution work
Agents should do the default work of:
- requirement shaping
- plan generation
- interface design
- implementation
- validation
- retry and repair
- documentation updates
- structured reporting of progress and failure

### 4.3 The harness mediates control
The harness is responsible for:
- routing work
- preserving structured state
- exposing approval boundaries
- classifying failures
- enabling retries
- making execution legible to both humans and agents

---

## 5. Core design principles

## 5.1 Agent-first
Normal progress should be agent-driven.

Humans should not be required to approve ordinary code writing or every local decision. If normal execution becomes approval-heavy, the system is no longer agent-first.

## 5.2 Human-controlled boundaries
Human judgment should be required only at explicit boundaries, such as:

- execute a generated plan
- accept structural step changes or backtracking
- allow risky command execution
- decide what to do after repeated failures

The human is not the runtime. The human is the control authority at defined boundaries.

## 5.3 Structured state over chat narration
The true system state must live in structured backend fields, not only in conversation text.

Chat is useful for:
- explanation
- refinement
- negotiation
- user intent updates

But chat must not be the only source of truth for:
- plan readiness
- run status
- pending approvals
- risk visibility
- failure escalation

## 5.4 Verification-first execution
Execution is not complete when code is written.
Execution is only meaningful when the agent can validate whether the step actually advanced the goal.

The harness should optimize for:
- reproducible execution
- testable step outcomes
- clear pass/fail signals
- retryable vs non-retryable failure classification
- evidence-backed progress

## 5.5 Repository as system of record
Anything important to agent behavior should be discoverable in the repository.

If knowledge only exists in:
- chat history
- Slack-like discussion
- human memory
- undocumented conventions

then for the agent it effectively does not exist.

The repository should gradually become the agent's working memory substrate:
- philosophy
- workflow rules
- architecture constraints
- node contracts
- execution plans
- quality rules
- known debt and anti-patterns

## 5.6 Legibility beats cleverness
Choose structures that are easier for agents to inspect, reason about, and validate.

Prefer:
- stable interfaces
- explicit contracts
- narrow responsibilities
- mechanically enforceable rules
- structured outputs

over opaque clever abstractions that may feel elegant to humans but are hard for agents to operate safely.

## 5.7 Boundaries should be enforced mechanically
A principle that only exists in prose is weak.

Over time, important rules should move into:
- tests
- linters
- schema checks
- state transition invariants
- contract validation

The ideal progression is:

1. observe drift
2. write the rule down
3. encode the rule into the system
4. make future drift cheaper to catch and correct

---

## 6. The role of the current backend

The current backend should be understood as the beginning of the harness control plane.

Its job is not only to move between nodes.
Its deeper job is to represent and control agent work in a product-meaningful way.

That is why fields like these matter:

- `plan_status`
- `run_status`
- `approval_required`
- `approval_type`
- `approval_payload`
- `pending_approvals`
- `risk_actions`

These fields are not UI decoration.
They are the system contract between:
- agent behavior
- orchestration logic
- frontend workspace
- human control

---

## 7. A clearer architecture lens

This project can be viewed as four layers:

### 7.1 Intent layer
Captures what the human wants.
Examples:
- goals
- requirements
- constraints
- plan modifications

### 7.2 Control layer
Controls state and workflow transitions.
Examples:
- graph routing
- run status
- approval boundaries
- retry escalation
- node contracts

### 7.3 Execution layer
Performs agent work.
Examples:
- planning
- interface generation
- coding
- validation
- repair loops

### 7.4 Evidence layer
Shows whether execution actually worked.
Examples:
- test results
- command outputs
- validation reports
- logs
- metrics
- screenshots
- structured failure summaries

A mature harness integrates all four layers.
A node graph alone is not yet a full harness.

---

## 8. The next project milestone should NOT be "more agents"

The next milestone should be:

## Build a reliable single-step execution loop

That means the system should be able to:

1. accept a human-approved plan
2. select one step
3. execute that step
4. validate the outcome
5. classify the result as one of:
   - success
   - retry automatically
   - wait for approval
   - blocked
   - failed
6. write the result back into structured state

This is more important than adding many new agent roles.
Without this loop, new nodes mostly increase surface area.
With this loop, new capabilities compound.

---

## 9. Recommended implementation priorities

## Priority 1: finish the control-plane semantics
Strengthen the state machine so the backend cleanly represents:
- plan lifecycle
- run lifecycle
- approval boundaries
- retry escalation
- node outcome contracts

## Priority 2: define node contracts explicitly
Each node should eventually have a clear contract for:
- expected inputs
- allowed state mutations
- success outputs
- failure outputs
- escalation conditions

## Priority 3: build verification harnesses
Invest in the structures that let the system prove work happened:
- validation result schemas
- normalized command/test outcomes
- failure classification
- evidence attachment to steps or runs

## Priority 4: make repo knowledge navigable for agents
Turn philosophy and workflow knowledge into a maintainable indexed repository knowledge base rather than scattered notes.

## Priority 5: encode principles mechanically
Add tests and guardrails for:
- state transitions
- approval boundary correctness
- contract consistency
- forbidden product-state regressions

---

## 10. Project quality bar

A good result for this project is not:

- the agent looked impressive in a demo
- the chat sounded smart
- a node produced code quickly once

A good result is:

- the system stayed legible
- the agent could operate with limited human intervention
- failures were classified instead of obscured
- approvals happened only at correct boundaries
- the repository accumulated reusable knowledge
- progress became more reliable over time, not more fragile

---

## 11. Working rule for future decisions

When deciding what to build next, prefer the change that most improves one of these:

1. agent legibility
2. control-boundary clarity
3. verification quality
4. recoverability after failure
5. repository-local knowledge quality
6. mechanical enforcement of important rules

If a proposed feature adds capability but weakens these, it is probably the wrong next step.

---

## 12. Final statement

This project is building the scaffolding for reliable agentic engineering.

The long-term goal is not to create a single agent that writes code.
The long-term goal is to create a harness where agents can:
- understand goals
- operate safely
- verify outcomes
- recover from failure
- collaborate with humans at the right boundaries
- improve as the repository becomes more legible and more enforceable

That is the product direction.
