import logging
import os
import re
from typing import Optional

from llm.openai_client import call_gpt

from agent.agent_prompt.coder_prompt import get_coder_system_prompt
from agent.state import (
    AgentState,
    EvidenceRecord,
    FailureCategory,
    NextNode,
    RunStatus,
    Step,
    StepOutcome,
    StepStatus,
)
from code_indexer.ast_checker import check_if_implemented
from code_indexer.get_workspace_skeleton import get_workspace_skeleton_direct
from tools.write_file_tool import write_file

logger = logging.getLogger(__name__)


def _make_evidence(
    *,
    kind: str,
    summary: str,
    passed: Optional[bool],
    step: Optional[Step] = None,
    details: Optional[dict] = None,
) -> EvidenceRecord:
    return EvidenceRecord(
        kind=kind,
        summary=summary,
        passed=passed,
        file_path=step.implementation_file if step else None,
        symbol_name=step.interface.name if step and step.interface else None,
        details=details or {},
    )


def _extract_python_code(text: str) -> Optional[str]:
    match = re.search(r"```python\s*\n(.*?)```", text, re.S)
    if match:
        return match.group(1).strip()
    match = re.search(r"```\s*\n(.*?)```", text, re.S)
    if match:
        return match.group(1).strip()
    return None


def _apply_search_replace(original_content: str, response_text: str) -> str:
    blocks = re.findall(r"<<<<\n(.*?)\n====\n(.*?)\n>>>>", response_text, flags=re.DOTALL)
    if not blocks:
        return original_content

    new_content = original_content
    for old_text, new_text in blocks:
        if old_text in new_content:
            new_content = new_content.replace(old_text, new_text, 1)
        else:
            logger.warning("Could not find the exact old_text block to replace.")
    return new_content


def _is_already_implemented(step: Step, workspace_skeleton: str, workspace_root: str) -> bool:
    if not step.interface:
        return False

    target_file = step.implementation_file
    if not target_file:
        return False

    full_path = os.path.join(workspace_root, target_file) if not os.path.isabs(target_file) else target_file
    return check_if_implemented(full_path, step.interface.name)


def _gather_dependency_context(step: Step, all_steps: list, workspace_root: str) -> str:
    if not step.interface or not step.interface.dependencies:
        return ""

    step_map = {s.id: s for s in all_steps}
    context_parts = []
    for dep_id in step.interface.dependencies:
        dep_step = step_map.get(dep_id)
        if not dep_step or not dep_step.interface:
            continue

        iface = dep_step.interface
        params_str = ", ".join(f"{p.name}: {p.type}" for p in iface.parameters)
        context_parts.append(
            f"--- Dependency Interface: {iface.name}({params_str}) -> {iface.return_type} ---\n"
            f"Description: {iface.description}\n"
        )

    return "\n".join(context_parts)


def _build_coder_prompt(step: Step, workspace_skeleton: str, dep_context: str, existing_content: str = None, failure_context: str = None) -> str:
    iface = step.interface
    params_str = ", ".join(f"{p.name}: {p.type}" for p in iface.parameters)

    prompt = f"""\
## Task: Implement Step {step.id} — {step.description}

### Target File
{step.implementation_file or "You decide the appropriate file path"}

### Primary Interface Specification
- Function name: {iface.name}
- Parameters: {params_str}
- Return type: {iface.return_type}
- Description: {iface.description}

### Project Architecture
{workspace_skeleton}
"""
    if dep_context:
        prompt += f"""
### Dependency Interfaces (Available to call)
{dep_context}
"""

    if step.extra_interfaces:
        extra_desc = "\n".join(
            f"- {i.name}({', '.join(p.name + ': ' + p.type for p in i.parameters)}) -> {i.return_type}: {i.description}"
            for i in step.extra_interfaces
        )
        prompt += f"""
### Additional Interfaces to Implement
{extra_desc}
"""

    if failure_context:
        prompt += f"""
### Previous Attempt Failed
The previous implementation attempt failed validation. Here is the failure evidence:
{failure_context}

Please fix the implementation to address the above failure.
"""

    if existing_content is not None:
        prompt += f"""
### Existing File Content
```python
{existing_content}
```

### Instructions
The target file already exists. Please implement the {iface.name} function by specifying SEARCH/REPLACE blocks.
Format your response exactly like this:
<<<<
old lines to remove
====
new lines to insert
>>>>
"""
    else:
        prompt += """
### Instructions
The target file is new. Please implement the function according to the specification above.
Return the COMPLETE file content in a single ```python code block.
"""
    return prompt


def _generate_test_file(step: Step, implementation_code: str, workspace_root: str) -> Optional[str]:
    """Generate a pytest test file for the step. Returns the test file path or None on failure."""
    iface = step.interface
    if not iface:
        return None

    all_interfaces = [iface] + list(step.extra_interfaces or [])
    interfaces_desc = "\n".join(
        f"- {i.name}({', '.join(p.name + ': ' + p.type for p in i.parameters)}) -> {i.return_type}: {i.description}"
        for i in all_interfaces
    )

    system_prompt = "You are a test writer. Write a pytest test file for the given function(s). Return only a ```python code block."
    user_prompt = (
        f"Interfaces:\n{interfaces_desc}\n\n"
        f"Implementation:\n```python\n{implementation_code}\n```\n\n"
        f"Write pytest tests covering normal cases and edge cases."
    )

    try:
        response = call_gpt(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            tools=None,
            temperature=0.2,
        )
        content = response["choices"][0]["message"]["content"]
        test_code = _extract_python_code(content)
        if not test_code:
            return None

        safe_id = step.id.replace("-", "_").replace(" ", "_")
        test_file_rel = f"tests/generated/test_{safe_id}.py"
        test_file_abs = os.path.join(workspace_root, test_file_rel)
        os.makedirs(os.path.dirname(test_file_abs), exist_ok=True)
        with open(test_file_abs, "w", encoding="utf-8") as f:
            f.write(test_code)
        return test_file_rel
    except Exception:
        logger.warning("Test generation failed for step %s — falling back to AST-only.", step.id)
        return None


def _dependencies_satisfied(step: Step, all_steps: list[Step]) -> bool:
    if not step.interface or not step.interface.dependencies:
        return True

    step_map = {candidate.id: candidate for candidate in all_steps}
    for dep_id in step.interface.dependencies:
        dep_step = step_map.get(dep_id)
        if dep_step is None or dep_step.status != StepStatus.SUCCESS:
            return False
    return True


def _select_first_executable_step(plan: list[Step]) -> tuple[Optional[int], Optional[Step]]:
    for index, step in enumerate(plan):
        if step.status != StepStatus.PENDING:
            continue
        if step.interface and not _dependencies_satisfied(step, plan):
            continue
        return index, step
    return None, None


def _execution_failure(
    *,
    plan: list[Step],
    step_index: Optional[int],
    step: Optional[Step],
    message: str,
    outcome: StepOutcome,
    run_status: RunStatus,
    failure_category: FailureCategory,
    evidence_kind: str,
):
    updated_plan = list(plan)
    if step is not None and step_index is not None:
        updated_plan[step_index] = step.model_copy(update={"status": StepStatus.FAILED})

    evidence = []
    if step is not None:
        evidence.append(
            _make_evidence(
                kind=evidence_kind,
                summary=message,
                passed=False,
                step=step,
                details={"failure_category": failure_category.value},
            )
        )

    return {
        "plan": updated_plan,
        "current_agent": NextNode.CODER,
        "next_node": None,
        "run_status": run_status,
        "last_error_message": message,
        "progress_text": message,
        "last_action_summary": message,
        "last_validation_summary": None,
        "last_validation_status": None,
        "last_validation_passed": None,
        "last_failure_category": failure_category,
        "last_evidence": evidence,
        "last_outcome": outcome,
        "approval_required": False,
        "approval_type": None,
        "approval_payload": None,
        "retrying_node": None,
    }


def coder_node(state: AgentState):
    logger.info("--- CODER NODE STARTING ---")

    if not state.plan:
        return {
            "current_agent": NextNode.CODER,
            "run_status": RunStatus.BLOCKED,
            "next_node": None,
            "last_error_message": "No approved plan is available for execution.",
            "progress_text": "No approved plan is available for execution.",
            "last_failure_category": FailureCategory.INVALID_TARGET,
            "last_evidence": [],
            "last_outcome": StepOutcome.BLOCKED,
        }

    if not state.workspace_root:
        return {
            "current_agent": NextNode.CODER,
            "run_status": RunStatus.BLOCKED,
            "next_node": None,
            "last_error_message": "workspace_root is required before execution can start.",
            "progress_text": "workspace_root is required before execution can start.",
            "last_failure_category": FailureCategory.INVALID_TARGET,
            "last_evidence": [],
            "last_outcome": StepOutcome.BLOCKED,
        }

    workspace_skeleton = get_workspace_skeleton_direct(state.workspace_root)
    plan = list(state.plan)
    step_index, step = _select_first_executable_step(plan)

    if step is None:
        pending_exists = any(candidate.status == StepStatus.PENDING for candidate in plan)
        message = (
            "Pending steps are blocked by unsatisfied dependencies."
            if pending_exists
            else "No pending executable steps remain."
        )
        return {
            "plan": plan,
            "current_agent": NextNode.CODER,
            "next_node": None,
            "run_status": RunStatus.BLOCKED if pending_exists else RunStatus.SUCCESS,
            "progress_text": message,
            "last_error_message": message if pending_exists else None,
            "last_failure_category": FailureCategory.INVALID_TARGET if pending_exists else None,
            "last_evidence": [],
            "last_outcome": StepOutcome.BLOCKED if pending_exists else StepOutcome.SUCCESS,
        }

    if not step.interface:
        return _execution_failure(
            plan=plan,
            step_index=step_index,
            step=step,
            message=f"Step {step.id} has no interface definition.",
            outcome=StepOutcome.BLOCKED,
            run_status=RunStatus.BLOCKED,
            failure_category=FailureCategory.INVALID_TARGET,
            evidence_kind="implementation_target",
        )

    target_file = step.implementation_file or f"src/{step.interface.name}.py"
    full_path = target_file if os.path.isabs(target_file) else os.path.join(state.workspace_root, target_file)
    action_summary = f"Implement step {step.id} in {target_file} for interface {step.interface.name}."

    running_step = step.model_copy(
        update={
            "status": StepStatus.RUNNING,
            "implementation_file": target_file,
        }
    )
    plan[step_index] = running_step

    if _is_already_implemented(running_step, workspace_skeleton, state.workspace_root):
        return {
            "plan": plan,
            "current_agent": NextNode.CODER,
            "current_step": step_index,
            "current_step_id": running_step.id,
            "current_step_title": running_step.description,
            "next_node": NextNode.TESTER,
            "run_status": RunStatus.RUNNING,
            "progress_text": f"Step {running_step.id} already appears implemented; validating.",
            "last_action_summary": f"Step {running_step.id} already exists in {target_file}; skipping code generation and moving to validation.",
            "last_validation_summary": None,
            "last_validation_status": None,
            "last_validation_passed": None,
            "last_failure_category": None,
            "last_evidence": [],
            "last_outcome": None,
            "last_error_message": None,
            "approval_required": False,
            "approval_type": None,
            "approval_payload": None,
        }

    dep_context = _gather_dependency_context(running_step, plan, state.workspace_root)

    # Build failure context from last evidence if this is a retry
    failure_context = None
    if step.retries > 0 and state.last_evidence:
        evidence_lines = []
        for ev in state.last_evidence:
            status = "PASSED" if ev.passed else "FAILED"
            evidence_lines.append(f"- [{status}] {ev.kind}: {ev.summary}")
            if ev.details:
                for k, v in ev.details.items():
                    evidence_lines.append(f"  {k}: {v}")
        failure_context = "\n".join(evidence_lines)
        if state.last_validation_summary:
            failure_context = f"Validation summary: {state.last_validation_summary}\n\nEvidence:\n" + failure_context

    existing_content = None
    if os.path.exists(full_path):
        try:
            with open(full_path, "r", encoding="utf-8") as file:
                existing_content = file.read()
        except Exception as exc:
            return _execution_failure(
                plan=plan,
                step_index=step_index,
                step=running_step,
                message=f"Failed to read target file {target_file}: {exc}",
                outcome=StepOutcome.BLOCKED,
                run_status=RunStatus.BLOCKED,
                failure_category=FailureCategory.EXECUTION_ERROR,
                evidence_kind="file_read",
            )

    user_prompt = _build_coder_prompt(running_step, workspace_skeleton, dep_context, existing_content, failure_context)

    is_new_file = existing_content is None
    is_new_func = True
    if existing_content and f"def {running_step.interface.name}" in existing_content:
        is_new_func = False

    if is_new_file:
        choice = 1
    elif is_new_func:
        choice = 3
    else:
        choice = 2

    coder_system_prompt = get_coder_system_prompt(choice=choice)
    messages = [
        {"role": "system", "content": coder_system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    try:
        response = call_gpt(messages=messages, tools=None, temperature=0.1)
        content = response["choices"][0]["message"]["content"]

        if existing_content is not None:
            code = _apply_search_replace(existing_content, content)
            if code == existing_content and "<<<<" not in content:
                fallback_code = _extract_python_code(content)
                if fallback_code:
                    code = fallback_code
                else:
                    return _execution_failure(
                        plan=plan,
                        step_index=step_index,
                        step=running_step,
                        message=f"LLM did not return a valid patch for step {running_step.id}.",
                        outcome=StepOutcome.FAILED,
                        run_status=RunStatus.FAILED,
                        failure_category=FailureCategory.EXECUTION_ERROR,
                        evidence_kind="codegen_response",
                    )
        else:
            code = _extract_python_code(content)
            if not code:
                return _execution_failure(
                    plan=plan,
                    step_index=step_index,
                    step=running_step,
                    message=f"LLM did not return a valid python code block for step {running_step.id}.",
                    outcome=StepOutcome.FAILED,
                    run_status=RunStatus.FAILED,
                    failure_category=FailureCategory.EXECUTION_ERROR,
                    evidence_kind="codegen_response",
                )

        write_result = write_file(path=target_file, content=code)
        if "successfully" not in write_result.lower():
            return _execution_failure(
                plan=plan,
                step_index=step_index,
                step=running_step,
                message=f"write_file failed for {target_file}: {write_result}",
                outcome=StepOutcome.FAILED,
                run_status=RunStatus.FAILED,
                failure_category=FailureCategory.EXECUTION_ERROR,
                evidence_kind="file_write",
            )

        test_file = _generate_test_file(running_step, code, state.workspace_root)
        if test_file:
            running_step = running_step.model_copy(update={"test_file": test_file})
            plan[step_index] = running_step

        return {
            "plan": plan,
            "current_agent": NextNode.CODER,
            "current_step": step_index,
            "current_step_id": running_step.id,
            "current_step_title": running_step.description,
            "next_node": NextNode.TESTER,
            "run_status": RunStatus.RUNNING,
            "progress_text": f"Implemented step {running_step.id}; starting validation.",
            "last_action_summary": action_summary,
            "last_validation_summary": None,
            "last_validation_status": None,
            "last_validation_passed": None,
            "last_failure_category": None,
            "last_evidence": [],
            "last_outcome": None,
            "last_error_message": None,
            "approval_required": False,
            "approval_type": None,
            "approval_payload": None,
            "retrying_node": None,
        }
    except Exception as exc:
        logger.exception("Step %s failed during code generation", running_step.id)
        return _execution_failure(
            plan=plan,
            step_index=step_index,
            step=running_step,
            message=f"Code generation failed for step {running_step.id}: {exc}",
            outcome=StepOutcome.FAILED,
            run_status=RunStatus.FAILED,
            failure_category=FailureCategory.EXECUTION_ERROR,
            evidence_kind="codegen_exception",
        )
