import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from agent.state import (
    AgentState,
    ApprovalRequest,
    ApprovalStatus,
    ApprovalType,
    EvidenceRecord,
    FailureCategory,
    NextNode,
    RunStatus,
    Step,
    StepOutcome,
    StepStatus,
    ValidationStatus,
)
from code_indexer.ast_checker import check_implementation_detail
from utils.test_runner import run_pytest

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

MAX_STEP_RETRIES = 2


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


def _find_current_step(plan: list[Step], step_id: Optional[str]) -> tuple[Optional[int], Optional[Step]]:
    if not step_id:
        return None, None
    for index, step in enumerate(plan):
        if step.id == step_id:
            return index, step
    return None, None


def _set_step(plan: list[Step], index: int, step: Step) -> list[Step]:
    updated = list(plan)
    updated[index] = step
    return updated


def _blocked_result(
    plan: list[Step],
    index: Optional[int],
    step: Optional[Step],
    message: str,
    *,
    failure_category: FailureCategory,
    evidence_kind: str = "validation_blocker",
):
    updated_plan = list(plan)
    if step is not None and index is not None:
        updated_plan[index] = step.model_copy(update={"status": StepStatus.FAILED})

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
        "current_agent": NextNode.TESTER,
        "next_node": None,
        "run_status": RunStatus.BLOCKED,
        "last_validation_status": ValidationStatus.BLOCKED,
        "last_validation_passed": False,
        "last_validation_summary": message,
        "last_failure_category": failure_category,
        "last_evidence": evidence,
        "last_error_message": message,
        "last_outcome": StepOutcome.BLOCKED,
        "progress_text": message,
        "approval_required": False,
        "approval_type": None,
        "approval_payload": None,
        "retrying_node": None,
    }


def _build_run_summary(plan: list) -> str:
    total = len(plan)
    success = sum(1 for s in plan if s.status == StepStatus.SUCCESS)
    failed = sum(1 for s in plan if s.status == StepStatus.FAILED)
    pending = sum(1 for s in plan if s.status == StepStatus.PENDING)
    running = sum(1 for s in plan if s.status == StepStatus.RUNNING)
    return f"{success}/{total} steps completed" + (
        f", {failed} failed" if failed else ""
    ) + (
        f", {pending} pending" if pending else ""
    ) + (
        f", {running} running" if running else ""
    )


def tester_node(state: AgentState):
    logger.info("[tester_node] start session=%s current_step_id=%s", getattr(state, "session_id", "<unknown>"), state.current_step_id)
    plan = list(state.plan or [])
    if not plan:
        logger.warning("[tester_node] no plan available to validate")
        return {
            "current_agent": NextNode.TESTER,
            "next_node": None,
            "run_status": RunStatus.BLOCKED,
            "last_validation_status": ValidationStatus.BLOCKED,
            "last_validation_passed": False,
            "last_validation_summary": "No plan is available to validate.",
            "last_failure_category": FailureCategory.INVALID_TARGET,
            "last_evidence": [],
            "last_error_message": "No plan is available to validate.",
            "last_outcome": StepOutcome.BLOCKED,
            "progress_text": "No plan is available to validate.",
        }

    step_index, step = _find_current_step(plan, state.current_step_id)
    if step is None or step_index is None:
        logger.error("[tester_node] current step not found in plan; current_step_id=%s", state.current_step_id)
        return {
            "current_agent": NextNode.TESTER,
            "next_node": None,
            "run_status": RunStatus.BLOCKED,
            "last_validation_status": ValidationStatus.BLOCKED,
            "last_validation_passed": False,
            "last_validation_summary": "Current execution step could not be found in the plan.",
            "last_failure_category": FailureCategory.INVALID_TARGET,
            "last_evidence": [],
            "last_error_message": "Current execution step could not be found in the plan.",
            "last_outcome": StepOutcome.BLOCKED,
            "progress_text": "Current execution step could not be found in the plan.",
        }

    if not state.workspace_root:
        logger.warning("[tester_node] workspace_root missing; cannot validate")
        return _blocked_result(
            plan,
            step_index,
            step,
            "workspace_root is required before validation can run.",
            failure_category=FailureCategory.INVALID_TARGET,
            evidence_kind="workspace_check",
        )

    if not step.interface or not step.interface.name:
        return _blocked_result(
            plan,
            step_index,
            step,
            f"Step {step.id} has no interface name for validation.",
            failure_category=FailureCategory.INVALID_TARGET,
            evidence_kind="validation_target",
        )

    if not step.implementation_file:
        return _blocked_result(
            plan,
            step_index,
            step,
            f"Step {step.id} has no implementation file to validate.",
            failure_category=FailureCategory.INVALID_TARGET,
            evidence_kind="validation_target",
        )

    full_path = step.implementation_file
    if not os.path.isabs(full_path):
        full_path = os.path.join(state.workspace_root, full_path)

    # 非 Python 代码（前端 / 资源文件等）只检查文件是否存在，存在即视为通过
    ext = os.path.splitext(full_path)[1].lower()
    if ext in {".jsx", ".js", ".tsx", ".ts", ".html", ".css", ".py"}:
        if not os.path.exists(full_path):
            return _blocked_result(
                plan,
                step_index,
                step,
                f"Implementation file does not exist: {step.implementation_file}",
                failure_category=FailureCategory.MISSING_FILE,
                evidence_kind="file_presence",
            )

        summary = f"Implementation file exists for {step.interface.name} at {step.implementation_file}."
        evidence = _make_evidence(
            kind="file_presence_check",
            summary=summary,
            passed=True,
            step=step,
            details={"file_path": step.implementation_file},
        )
        success_step = step.model_copy(update={"status": StepStatus.SUCCESS})
        updated_plan = _set_step(plan, step_index, success_step)
        has_more = any(s.status == StepStatus.PENDING for s in updated_plan)
        next_run_status = RunStatus.RUNNING if has_more else RunStatus.SUCCESS
        return {
            "plan": updated_plan,
            "current_agent": NextNode.TESTER,
            "next_node": None,
            "run_status": next_run_status,
            "last_validation_status": ValidationStatus.PASSED,
            "last_validation_passed": True,
            "last_validation_summary": summary,
            "last_failure_category": None,
            "last_evidence": [evidence],
            "last_error_message": None,
            "last_outcome": StepOutcome.SUCCESS,
            "progress_text": f"Step {step.id} validated successfully (file existence only).",
            "approval_required": False,
            "approval_type": None,
            "approval_payload": None,
            "retry_count": 0,
            "retrying_node": None,
            "run_summary": _build_run_summary(updated_plan),
        }

    if not os.path.exists(full_path):
        return _blocked_result(
            plan,
            step_index,
            step,
            f"Implementation file does not exist: {step.implementation_file}",
            failure_category=FailureCategory.MISSING_FILE,
            evidence_kind="file_presence",
        )

    expected_param_count = len(step.interface.parameters) if step.interface.parameters else 0
    check = check_implementation_detail(full_path, step.interface.name, expected_param_count=expected_param_count)

    check_detail = {
        "validator": "check_implementation_detail",
        "detail": check.detail,
        "actual_params": check.actual_params,
        "expected_param_count": expected_param_count,
        "param_count_match": check.param_count_match,
    }

    if check.passed():
        ast_summary = f"Validated {step.interface.name} in {step.implementation_file}. {check.detail}"
        ast_evidence = _make_evidence(
            kind="ast_symbol_check",
            summary=ast_summary,
            passed=True,
            step=step,
            details=check_detail,
        )

        if step.test_file:
            test_file_abs = step.test_file if os.path.isabs(step.test_file) else os.path.join(state.workspace_root, step.test_file)
            if os.path.exists(test_file_abs):
                pytest_result = run_pytest(test_file_abs, state.workspace_root)
                pytest_evidence = _make_evidence(
                    kind="pytest_run",
                    summary=f"pytest {'passed' if pytest_result.passed else 'failed'}: {step.test_file}",
                    passed=pytest_result.passed,
                    step=step,
                    details={
                        "return_code": pytest_result.return_code,
                        "output": pytest_result.output[:2000],
                        "test_file": step.test_file,
                    },
                )
                if not pytest_result.passed:
                    failure_summary = f"pytest failed for {step.interface.name}: {step.test_file}"
                    next_retries = step.retries + 1
                    failure_evidence = [ast_evidence, pytest_evidence]
                    if next_retries >= MAX_STEP_RETRIES:
                        failed_step = step.model_copy(update={"status": StepStatus.FAILED, "retries": next_retries})
                        updated_plan = _set_step(plan, step_index, failed_step)
                        approval = ApprovalRequest(
                            id=str(uuid.uuid4()),
                            type=ApprovalType.RETRY_AFTER_FAILURE,
                            title=f"Retry step {step.id} after pytest failure",
                            description=f"Step {step.id} exhausted retry budget. pytest failed.",
                            created_at=datetime.now(timezone.utc).isoformat(),
                            step_id=step.id,
                            blocking=True,
                            status=ApprovalStatus.PENDING,
                            requested_action="retry_after_failure",
                            reason=failure_summary,
                            payload={
                                "step_id": step.id,
                                "retry_count": next_retries,
                                "max_retries": MAX_STEP_RETRIES,
                                "failure_category": FailureCategory.MISSING_IMPLEMENTATION.value,
                            },
                        )
                        return {
                            "plan": updated_plan,
                            "current_agent": NextNode.TESTER,
                            "next_node": None,
                            "run_status": RunStatus.WAITING_APPROVAL,
                            "last_validation_status": ValidationStatus.FAILED,
                            "last_validation_passed": False,
                            "last_validation_summary": failure_summary,
                            "last_failure_category": FailureCategory.MISSING_IMPLEMENTATION,
                            "last_evidence": failure_evidence,
                            "last_error_message": failure_summary,
                            "last_outcome": StepOutcome.WAITING_APPROVAL,
                            "progress_text": f"Step {step.id} exhausted retry budget after pytest failure.",
                            "approval_required": True,
                            "approval_type": ApprovalType.RETRY_AFTER_FAILURE,
                            "approval_payload": {
                                "step_id": step.id,
                                "reason": "retry_budget_exhausted",
                                "retry_count": next_retries,
                                "max_retries": MAX_STEP_RETRIES,
                                "failure_category": FailureCategory.MISSING_IMPLEMENTATION.value,
                            },
                            "pending_approvals": list(state.pending_approvals) + [approval],
                            "retry_count": next_retries,
                            "retrying_node": None,
                            "run_summary": _build_run_summary(_set_step(plan, step_index, failed_step)),
                        }
                    retry_step = step.model_copy(update={"status": StepStatus.PENDING, "retries": next_retries})
                    updated_plan = _set_step(plan, step_index, retry_step)
                    return {
                        "plan": updated_plan,
                        "current_agent": NextNode.TESTER,
                        "next_node": NextNode.CODER,
                        "run_status": RunStatus.RUNNING,
                        "last_validation_status": ValidationStatus.FAILED,
                        "last_validation_passed": False,
                        "last_validation_summary": failure_summary,
                        "last_failure_category": FailureCategory.MISSING_IMPLEMENTATION,
                        "last_evidence": failure_evidence,
                        "last_error_message": failure_summary,
                        "last_outcome": StepOutcome.RETRY,
                        "progress_text": f"Retrying step {step.id} after pytest failure.",
                        "approval_required": False,
                        "approval_type": None,
                        "approval_payload": None,
                        "retry_count": next_retries,
                        "retrying_node": NextNode.CODER.value,
                        "run_summary": _build_run_summary(updated_plan),
                    }
                success_evidence = [ast_evidence, pytest_evidence]
            else:
                success_evidence = [ast_evidence]
        else:
            success_evidence = [ast_evidence]

        success_summary = ast_summary
        success_step = step.model_copy(update={"status": StepStatus.SUCCESS})
        updated_plan = _set_step(plan, step_index, success_step)
        has_more = any(s.status == StepStatus.PENDING for s in updated_plan)
        next_run_status = RunStatus.RUNNING if has_more else RunStatus.SUCCESS
        return {
            "plan": updated_plan,
            "current_agent": NextNode.TESTER,
            "next_node": None,
            "run_status": next_run_status,
            "last_validation_status": ValidationStatus.PASSED,
            "last_validation_passed": True,
            "last_validation_summary": success_summary,
            "last_failure_category": None,
            "last_evidence": success_evidence,
            "last_error_message": None,
            "last_outcome": StepOutcome.SUCCESS,
            "progress_text": f"Step {step.id} validated successfully.",
            "approval_required": False,
            "approval_type": None,
            "approval_payload": None,
            "retry_count": 0,
            "retrying_node": None,
            "run_summary": _build_run_summary(updated_plan),
        }

    failure_summary = f"Validation failed for {step.interface.name} in {step.implementation_file}. {check.detail}"
    next_retries = step.retries + 1
    failure_evidence = [
        _make_evidence(
            kind="ast_symbol_check",
            summary=failure_summary,
            passed=False,
            step=step,
            details=check_detail,
        )
    ]

    if next_retries >= MAX_STEP_RETRIES:
        failed_step = step.model_copy(update={"status": StepStatus.FAILED, "retries": next_retries})
        updated_plan = _set_step(plan, step_index, failed_step)
        approval = ApprovalRequest(
            id=str(uuid.uuid4()),
            type=ApprovalType.RETRY_AFTER_FAILURE,
            title=f"Retry step {step.id} after failure",
            description=f"Step {step.id} exhausted retry budget. Manual review required.",
            created_at=datetime.now(timezone.utc).isoformat(),
            step_id=step.id,
            blocking=True,
            status=ApprovalStatus.PENDING,
            requested_action="retry_after_failure",
            reason=failure_summary,
            payload={
                "step_id": step.id,
                "retry_count": next_retries,
                "max_retries": MAX_STEP_RETRIES,
                "failure_category": FailureCategory.MISSING_IMPLEMENTATION.value,
            },
        )
        return {
            "plan": updated_plan,
            "current_agent": NextNode.TESTER,
            "next_node": None,
            "run_status": RunStatus.WAITING_APPROVAL,
            "last_validation_status": ValidationStatus.FAILED,
            "last_validation_passed": False,
            "last_validation_summary": failure_summary,
            "last_failure_category": FailureCategory.MISSING_IMPLEMENTATION,
            "last_evidence": failure_evidence,
            "last_error_message": failure_summary,
            "last_outcome": StepOutcome.WAITING_APPROVAL,
            "progress_text": f"Step {step.id} exhausted retry budget and is waiting for approval.",
            "approval_required": True,
            "approval_type": ApprovalType.RETRY_AFTER_FAILURE,
            "approval_payload": {
                "step_id": step.id,
                "reason": "retry_budget_exhausted",
                "retry_count": next_retries,
                "max_retries": MAX_STEP_RETRIES,
                "last_validation_summary": failure_summary,
                "failure_category": FailureCategory.MISSING_IMPLEMENTATION.value,
            },
            "pending_approvals": list(state.pending_approvals) + [approval],
            "retry_count": next_retries,
            "retrying_node": None,
            "run_summary": _build_run_summary(updated_plan),
        }

    retry_step = step.model_copy(update={"status": StepStatus.PENDING, "retries": next_retries})
    updated_plan = _set_step(plan, step_index, retry_step)
    return {
        "plan": updated_plan,
        "current_agent": NextNode.TESTER,
        "next_node": NextNode.CODER,
        "run_status": RunStatus.RUNNING,
        "last_validation_status": ValidationStatus.FAILED,
        "last_validation_passed": False,
        "last_validation_summary": failure_summary,
        "last_failure_category": FailureCategory.MISSING_IMPLEMENTATION,
        "last_evidence": failure_evidence,
        "last_error_message": failure_summary,
        "last_outcome": StepOutcome.RETRY,
        "progress_text": f"Retrying step {step.id} after failed validation.",
        "approval_required": False,
        "approval_type": None,
        "approval_payload": None,
        "retry_count": next_retries,
        "retrying_node": NextNode.CODER.value,
        "run_summary": _build_run_summary(updated_plan),
    }
