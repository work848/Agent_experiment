# Validation Evidence Schema

> Reference for all validation-related data structures, failure categories, and the AST checker contract.
> Derived from: `state.py`, `ast_checker.py`, `tester_node.py`.

---

## 1. EvidenceRecord

Defined in `src/agent/state.py`. Attached to `AgentState.last_evidence` after every validation attempt.

```python
class EvidenceRecord(BaseModel):
    kind: str                          # see §2 below
    summary: str                       # human-readable one-line result
    passed: Optional[bool]             # True / False / None (inconclusive)
    file_path: Optional[str]           # implementation file checked
    symbol_name: Optional[str]         # function/class name checked
    details: Dict[str, Any]            # validator-specific structured data
```

### `details` shape by `kind`

| kind | details keys |
|------|--------------|
| `ast_symbol_check` | `validator`, `detail`, `actual_params`, `expected_param_count`, `param_count_match` |
| `codegen_response` | `raw_response`, `failure_category` |
| `validation_blocker` | `failure_category` |
| `file_presence` | `failure_category` |
| `validation_target` | `failure_category` |
| `workspace_check` | `failure_category` |

---

## 2. Evidence Kinds

| kind | Produced by | Meaning |
|------|-------------|----------|
| `ast_symbol_check` | `tester_node` | AST-level check via `check_implementation_detail` |
| `codegen_response` | `coder_node` | Raw LLM output could not be parsed as valid code |
| `validation_blocker` | `tester_node` (`_blocked_result`) | Generic pre-check failure |
| `file_presence` | `tester_node` | Implementation file does not exist on disk |
| `validation_target` | `tester_node` | Step has no interface name or no implementation file |
| `workspace_check` | `tester_node` | `workspace_root` not set |

---

## 3. ValidationStatus

Defined in `src/agent/state.py`. Written to `AgentState.last_validation_status`.

| Value | Meaning |
|-------|---------|
| `passed` | Validation ran and succeeded |
| `failed` | Validation ran and failed (retryable or escalatable) |
| `blocked` | Validation could not run due to missing prerequisite |

---

## 4. FailureCategory

Defined in `src/agent/state.py`. Written to `AgentState.last_failure_category` and included in `EvidenceRecord.details`.

| Value | Meaning | Typical source |
|-------|---------|----------------|
| `missing_implementation` | Symbol not found in file, or param count mismatch | `tester_node` AST check failure |
| `missing_file` | Implementation file does not exist | `tester_node` file presence check |
| `invalid_target` | Step has no interface name, no file, or no workspace | `tester_node` pre-checks |
| `execution_error` | Coder LLM output could not be parsed as code | `coder_node` |
| `unknown` | Unclassified failure | fallback |

---

## 5. check_implementation_detail Contract

Defined in `src/code_indexer/ast_checker.py`.

```python
def check_implementation_detail(
    file_path: str,
    interface_name: str,
    expected_param_count: Optional[int] = None,
) -> ImplementationCheckResult
```

### ImplementationCheckResult fields

| Field | Type | Meaning |
|-------|------|---------|
| `found` | `bool` | Symbol exists in file (top-level only) |
| `param_count_match` | `Optional[bool]` | `None` if not checked; `True/False` if checked |
| `actual_params` | `list[str]` | Parameter names found (excluding `self`) |
| `expected_params` | `Optional[int]` | The expected count passed in |
| `detail` | `str` | Human-readable summary of the check result |

### `.passed()` logic

```python
def passed(self) -> bool:
    if not self.found:              # symbol missing → fail
        return False
    if self.param_count_match is False:  # wrong param count → fail
        return False
    return True
```

### Limitations

- Only checks **top-level** `def`, `async def`, and `class` — nested functions are not found.
- Does not check return type or parameter types, only names and count.
- Does not execute the function; purely static AST analysis.
- `SyntaxError` in the target file → `found=False`, detail contains error message.

---

## 6. ValidationSummary (composite model)

Defined in `src/agent/state.py`. Not yet used as a return type by nodes — currently fields are written individually to `AgentState`. May be used as a structured sub-model in future.

```python
class ValidationSummary(BaseModel):
    status: ValidationStatus
    summary: str
    failure_category: Optional[FailureCategory] = None
    evidence: List[EvidenceRecord] = []
```

---

## 7. State Fields Written After Validation

All written by `tester_node` into the return dict:

| Field | Type | Notes |
|-------|------|-------|
| `last_validation_status` | `ValidationStatus` | `passed` / `failed` / `blocked` |
| `last_validation_passed` | `Optional[bool]` | Convenience bool mirror of status |
| `last_validation_summary` | `str` | Human-readable summary |
| `last_failure_category` | `Optional[FailureCategory]` | `None` on success |
| `last_evidence` | `List[EvidenceRecord]` | One record per check performed |
| `last_outcome` | `StepOutcome` | `success` / `retry` / `waiting_approval` / `blocked` / `failed` |
| `run_summary` | `str` | e.g. `"2/3 steps completed, 1 pending"` — built by `_build_run_summary` |

---

## 8. run_summary Format

Produced by `tester_node._build_run_summary(plan)`:

```
"{success}/{total} steps completed[, {failed} failed][, {pending} pending][, {running} running]"
```

Example: `"1/3 steps completed, 1 failed, 1 pending"`
