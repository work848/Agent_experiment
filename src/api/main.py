import os
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent.graph.build_graph import build_graph
from agent.state import (
    AgentState, Mode, NextNode, PlanStatus, RunStatus,
    StepStatus, UserAction,
)
from utils.action_policy import PolicyDecision, evaluate_action
from utils.approval_flow import ApprovalDecision, ApprovalResolution, resolve_approval
from utils.requirements_export import export_requirements_snapshot
from utils.restore_state import load_latest_state, load_session_state, load_state
from utils.save_state import save_session_state, save_state
from utils.user_action import handle_user_action

load_dotenv(dotenv_path="APIKey.env")
load_dotenv(dotenv_path="workspace.env") 
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

graph = build_graph()

# session memory
conversations: Dict[str, Dict[str, Any]] = {}


class ApprovalResolutionRequest(BaseModel):
    approval_id: str
    decision: str  # "approved" | "rejected"
    note: Optional[str] = None


class ChatRequest(BaseModel):
    session_id: str
    message: Optional[Union[str, List[str]]] = None
    plan: Optional[List[Dict[str, Any]]] = None
    trigger_plan: bool = False
    interface_refresh: bool = False
    last_user_action: Optional[UserAction] = None
    next_node: Optional[NextNode] = None
    mode: Mode = Mode.CHAT
    workspace_root: Optional[str] = None
    approval_resolution: Optional[ApprovalResolutionRequest] = None


class PlanGenerateRequest(BaseModel):
    session_id: str
    workspace_root: Optional[str] = None
    plan: Optional[List[Dict[str, Any]]] = None


class PlanModifyRequest(BaseModel):
    session_id: str
    instruction: str
    workspace_root: Optional[str] = None
    plan: Optional[List[Dict[str, Any]]] = None


class PlanSaveRequest(BaseModel):
    session_id: str
    workspace_root: Optional[str] = None
    plan: List[Dict[str, Any]]


class PlanExecuteRequest(BaseModel):
    session_id: str
    workspace_root: Optional[str] = None
    plan: Optional[List[Dict[str, Any]]] = None


class ApprovalResolveRequest(BaseModel):
    session_id: str
    approval_id: str
    decision: str
    note: Optional[str] = None


class ReloadStateRequest(BaseModel):
    session_id: str


class ResetStateRequest(BaseModel):
    session_id: str
    reset_persisted: bool = True


class MarkStepRequest(BaseModel):
    session_id: str
    step_id: str
    status: str


def _to_plain(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return {k: _to_plain(v) for k, v in value.model_dump().items()}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {k: _to_plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_plain(v) for v in value]
    return value


def _normalize_plan(plan: Any) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    if not isinstance(plan, list):
        return normalized

    for step in plan:
        step_dict = _to_plain(step) if not isinstance(step, dict) else _to_plain(step)
        status = str(step_dict.get("status", "pending") or "pending")
        # AgentState.StepStatus uses: "pending", "running", "success", "failed"
        if status not in {"pending", "running", "success", "failed"}:
            status = "pending"
        step_dict["status"] = status
        normalized.append(step_dict)

    return normalized


def _normalize_requirements(requirements: Any) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    if not isinstance(requirements, list):
        return normalized

    for req in requirements:
        req_dict = _to_plain(req) if not isinstance(req, dict) else _to_plain(req)
        req_dict["id"] = str(req_dict.get("id", ""))
        req_dict["priority"] = int(req_dict.get("priority", 3) or 3)
        req_dict["acceptance_criteria"] = [
            str(item) for item in (req_dict.get("acceptance_criteria") or [])
        ]
        req_dict["step_ids"] = [str(item) for item in (req_dict.get("step_ids") or [])]
        status = req_dict.get("status")
        if status not in {"pending", "in_progress", "done", "blocked"}:
            req_dict["status"] = "pending"
        normalized.append(req_dict)

    return normalized


def _derive_agents(result: Dict[str, Any]) -> Dict[str, str]:
    agents = {
        "planner": "idle",
        "coder": "idle",
        "tester": "idle",
    }

    current_agent = result.get("current_agent")
    if isinstance(current_agent, Enum):
        current_agent = current_agent.value

    retrying_node = result.get("retrying_node")
    if isinstance(retrying_node, Enum):
        retrying_node = retrying_node.value

    if current_agent in {"planner", "interface"} or retrying_node in {"planner", "interface"}:
        agents["planner"] = "working"
    elif current_agent == "coder":
        agents["coder"] = "working"
    elif current_agent == "tester":
        agents["tester"] = "working"

    return agents


def _derive_logs(result: Dict[str, Any]) -> List[str]:
    logs = result.get("logs")
    if isinstance(logs, list):
        return [str(item) for item in logs]

    mailbox = result.get("mailbox")
    if isinstance(mailbox, list):
        derived: List[str] = []
        for item in mailbox:
            if isinstance(item, dict):
                source = item.get("source", "agent")
                target = item.get("target", "agent")
                content = item.get("content", "")
                derived.append(f"[{source} -> {target}] {content}")
            else:
                derived.append(str(item))
        return derived

    return []


def _build_execution_summary(plan: List[Dict[str, Any]]) -> Dict[str, Any]:
    total_steps = len(plan)
    # 后端 StepStatus 使用的是: "pending" | "running" | "success" | "failed"
    # 这里将 "success" 以及历史遗留的 "done" 都视为已完成
    completed_steps = sum(1 for step in plan if step.get("status") in {"success", "done"})
    failed_steps = sum(1 for step in plan if step.get("status") == "failed")
    pending_steps = sum(1 for step in plan if step.get("status") == "pending")
    running_steps = sum(1 for step in plan if step.get("status") == "running")
    return {
        "total_steps": total_steps,
        "completed_steps": completed_steps,
        "failed_steps": failed_steps,
        "pending_steps": pending_steps,
        "running_steps": running_steps,
        "all_steps_completed": total_steps > 0 and completed_steps == total_steps,
    }


def _build_persistence_summary(state: AgentState) -> Dict[str, Any]:
    persisted_file = getattr(state, "persisted_file", None)
    return {
        "has_persisted_state": bool(persisted_file),
        "persisted_file": persisted_file,
        "last_saved_at": getattr(state, "last_saved_at", None),
        "last_restored_at": getattr(state, "last_restored_at", None),
        "restored_from_disk": bool(getattr(state, "restored_from_disk", False)),
        "updated_at": getattr(state, "updated_at", None),
    }


def _build_state_response(state: AgentState) -> Dict[str, Any]:
    plan = _normalize_plan(getattr(state, "plan", []))
    requirements = _normalize_requirements(getattr(state, "requirements", []))
    tool_events = _to_plain(getattr(state, "tool_events", []))
    last_tool_event = _to_plain(getattr(state, "last_tool_event", None))
    return {
        "session_id": getattr(state, "session_id", None),
        "mode": _to_plain(getattr(state, "mode", Mode.CHAT)),
        "current_agent": _to_plain(getattr(state, "current_agent", NextNode.CHAT)),
        "plan": plan,
        "requirements": requirements,
        "current_step": int(getattr(state, "current_step", 0) or 0),
        "current_step_id": getattr(state, "current_step_id", None),
        "current_step_title": getattr(state, "current_step_title", None),
        "agents": _derive_agents({
            "current_agent": getattr(state, "current_agent", NextNode.CHAT),
            "retrying_node": getattr(state, "retrying_node", None),
        }),
        "logs": _derive_logs({"mailbox": getattr(state, "mailbox", [])}),
        "messages": list(getattr(state, "messages", []))[-12:],
        "ready_for_plan": bool(getattr(state, "ready_for_plan", False)),
        "actions": getattr(state, "suggested_actions", []),
        "last_error_message": getattr(state, "last_error_message", None),
        "retry_count": int(getattr(state, "retry_count", 0) or 0),
        "retrying_node": getattr(state, "retrying_node", None),
        "progress_text": getattr(state, "progress_text", None),
        "last_action_summary": getattr(state, "last_action_summary", None),
        "last_validation_summary": getattr(state, "last_validation_summary", None),
        "last_validation_status": _to_plain(getattr(state, "last_validation_status", None)),
        "last_validation_passed": getattr(state, "last_validation_passed", None),
        "last_failure_category": _to_plain(getattr(state, "last_failure_category", None)),
        "last_evidence": _to_plain(getattr(state, "last_evidence", [])),
        "last_outcome": _to_plain(getattr(state, "last_outcome", None)),
        "execution": _build_execution_summary(plan),
        "persistence": _build_persistence_summary(state),
        "tool_events": tool_events,
        "last_tool_event": last_tool_event,
        # --- product-state fields ---
        "goal": _to_plain(getattr(state, "goal", None)),
        "plan_status": _to_plain(getattr(state, "plan_status", PlanStatus.DRAFT)),
        "run_status": _to_plain(getattr(state, "run_status", RunStatus.IDLE)),
        "approval_required": bool(getattr(state, "approval_required", False)),
        "approval_type": _to_plain(getattr(state, "approval_type", None)),
        "approval_payload": getattr(state, "approval_payload", None),
        "pending_approvals": _to_plain(getattr(state, "pending_approvals", [])),
        "risk_actions": _to_plain(getattr(state, "risk_actions", [])),
        "run_summary": getattr(state, "run_summary", None),
    }


def _empty_session() -> Dict[str, Any]:
    return {
        "messages": [],
        "current_agent": NextNode.CHAT,
        "mode": Mode.CHAT,
        "plan": None,
        "requirements": [],
        "current_step": 0,
        "current_step_id": None,
        "current_step_title": None,
        "mailbox": [],
        "consumed_last_user_action": None,
        "ready_for_plan": False,
        "suggested_actions": [],
        "workspace_root": None,
        "next_node": NextNode.CHAT,
        "last_failed_node": None,
        "last_error_message": None,
        "retry_count": 0,
        "max_node_retries": 1,
        "retrying_node": None,
        "progress_text": None,
        "last_action_summary": None,
        "last_validation_summary": None,
        "last_validation_status": None,
        "last_validation_passed": None,
        "last_failure_category": None,
        "last_evidence": [],
        "last_outcome": None,
        # --- product-state fields ---
        "goal": None,
        "plan_status": PlanStatus.DRAFT,
        "run_id": None,
        "run_status": RunStatus.IDLE,
        "approval_required": False,
        "approval_type": None,
        "approval_payload": None,
        "pending_approvals": [],
        "risk_actions": [],
        "run_summary": None,
        "tool_events": [],
        "last_tool_event": None,
        "last_saved_at": None,
        "last_restored_at": None,
        "persisted_file": None,
        "restored_from_disk": False,
        "updated_at": None,
    }


def _session_to_state(session_id: str, session: Dict[str, Any]) -> AgentState:
    return AgentState(
        session_id=session_id,
        messages=session.get("messages", []),
        workspace_root=session.get("workspace_root"),
        plan=session.get("plan"),
        requirements=_normalize_requirements(session.get("requirements", [])),
        current_step=session.get("current_step", 0),
        current_step_id=session.get("current_step_id"),
        current_step_title=session.get("current_step_title"),
        mailbox=session.get("mailbox", []),
        current_agent=session.get("current_agent", NextNode.CHAT),
        mode=session.get("mode", Mode.CHAT),
        trigger_plan=False,
        interface_refresh=False,
        last_user_action=None,
        next_node=session.get("next_node", NextNode.CHAT),
        tool_call=None,
        tool_events=session.get("tool_events", []),
        last_tool_event=session.get("last_tool_event"),
        iterations=0,
        max_iterations=5,
        ready_for_plan=bool(session.get("ready_for_plan", False)),
        suggested_actions=session.get("suggested_actions", []),
        last_failed_node=session.get("last_failed_node"),
        last_error_message=session.get("last_error_message"),
        retry_count=int(session.get("retry_count", 0) or 0),
        max_node_retries=int(session.get("max_node_retries", 1) or 1),
        retrying_node=session.get("retrying_node"),
        progress_text=session.get("progress_text"),
        last_action_summary=session.get("last_action_summary"),
        last_validation_summary=session.get("last_validation_summary"),
        last_validation_status=session.get("last_validation_status"),
        last_validation_passed=session.get("last_validation_passed"),
        last_failure_category=session.get("last_failure_category"),
        last_evidence=session.get("last_evidence", []),
        last_outcome=session.get("last_outcome"),
        # --- product-state fields ---
        goal=session.get("goal"),
        plan_status=session.get("plan_status", PlanStatus.DRAFT),
        run_id=session.get("run_id"),
        run_status=session.get("run_status", RunStatus.IDLE),
        approval_required=bool(session.get("approval_required", False)),
        approval_type=session.get("approval_type"),
        approval_payload=session.get("approval_payload"),
        pending_approvals=session.get("pending_approvals", []),
        risk_actions=session.get("risk_actions", []),
        run_summary=session.get("run_summary"),
        last_saved_at=session.get("last_saved_at"),
        last_restored_at=session.get("last_restored_at"),
        persisted_file=session.get("persisted_file"),
        restored_from_disk=bool(session.get("restored_from_disk", False)),
        updated_at=session.get("updated_at"),
    )


def _load_session_state(session_id: Optional[str]) -> Optional[AgentState]:
    if not session_id:
        return None
    state = load_session_state(AgentState, session_id)
    if state is not None:
        return state
    session = conversations.get(session_id)
    if not session:
        return None
    return _session_to_state(session_id, session)


def _load_persisted_state() -> Optional[AgentState]:
    state = load_state(AgentState)
    if state is not None:
        return state
    return load_latest_state(AgentState)


def _hydrate_session_cache(state: AgentState):
    conversations[state.session_id] = {
        "messages": list(getattr(state, "messages", [])),
        "current_agent": _to_plain(getattr(state, "current_agent", NextNode.CHAT)),
        "mode": _to_plain(getattr(state, "mode", Mode.CHAT)),
        "plan": _to_plain(getattr(state, "plan", None)),
        "requirements": _normalize_requirements(getattr(state, "requirements", [])),
        "current_step": int(getattr(state, "current_step", 0) or 0),
        "current_step_id": getattr(state, "current_step_id", None),
        "current_step_title": getattr(state, "current_step_title", None),
        "mailbox": _to_plain(getattr(state, "mailbox", [])),
        "consumed_last_user_action": None,
        "ready_for_plan": bool(getattr(state, "ready_for_plan", False)),
        "suggested_actions": _to_plain(getattr(state, "suggested_actions", [])),
        "workspace_root": getattr(state, "workspace_root", None),
        "next_node": _to_plain(getattr(state, "next_node", NextNode.CHAT)),
        "last_failed_node": _to_plain(getattr(state, "last_failed_node", None)),
        "last_error_message": getattr(state, "last_error_message", None),
        "retry_count": int(getattr(state, "retry_count", 0) or 0),
        "max_node_retries": int(getattr(state, "max_node_retries", 1) or 1),
        "retrying_node": getattr(state, "retrying_node", None),
        "progress_text": getattr(state, "progress_text", None),
        "last_action_summary": getattr(state, "last_action_summary", None),
        "last_validation_summary": getattr(state, "last_validation_summary", None),
        "last_validation_status": _to_plain(getattr(state, "last_validation_status", None)),
        "last_validation_passed": getattr(state, "last_validation_passed", None),
        "last_failure_category": _to_plain(getattr(state, "last_failure_category", None)),
        "last_evidence": _to_plain(getattr(state, "last_evidence", [])),
        "last_outcome": _to_plain(getattr(state, "last_outcome", None)),
        "goal": _to_plain(getattr(state, "goal", None)),
        "plan_status": _to_plain(getattr(state, "plan_status", PlanStatus.DRAFT)),
        "run_id": getattr(state, "run_id", None),
        "run_status": _to_plain(getattr(state, "run_status", RunStatus.IDLE)),
        "approval_required": bool(getattr(state, "approval_required", False)),
        "approval_type": _to_plain(getattr(state, "approval_type", None)),
        "approval_payload": _to_plain(getattr(state, "approval_payload", None)),
        "pending_approvals": _to_plain(getattr(state, "pending_approvals", [])),
        "risk_actions": _to_plain(getattr(state, "risk_actions", [])),
        "run_summary": getattr(state, "run_summary", None),
        "tool_events": _to_plain(getattr(state, "tool_events", [])),
        "last_tool_event": _to_plain(getattr(state, "last_tool_event", None)),
        "last_saved_at": getattr(state, "last_saved_at", None),
        "last_restored_at": getattr(state, "last_restored_at", None),
        "persisted_file": getattr(state, "persisted_file", None),
        "restored_from_disk": bool(getattr(state, "restored_from_disk", False)),
        "updated_at": getattr(state, "updated_at", None),
    }


def _get_or_create_session(session_id: str) -> Dict[str, Any]:
    return conversations.setdefault(session_id, _empty_session())


def _build_state_from_session(session_id: str, session: Dict[str, Any]) -> AgentState:
    return _session_to_state(session_id, session)


def _resolve_workspace_root(
    session: Dict[str, Any],
    workspace_root: Optional[str],
    *,
    required: bool,
) -> Optional[str]:
    resolved_workspace_root = workspace_root or session.get("workspace_root") or os.getenv("WORKSPACE_ROOT")
    if required and not resolved_workspace_root:
        raise HTTPException(
            status_code=400,
            detail="workspace_root is required. Pass it in the payload or set WORKSPACE_ROOT env variable.",
        )
    if resolved_workspace_root:
        session["workspace_root"] = resolved_workspace_root
    return resolved_workspace_root


def _normalize_message_content(message: Optional[Union[str, List[str]]]) -> Optional[str]:
    if isinstance(message, list):
        combined = "\n".join(str(x) for x in message)
        return combined.strip() or None
    if isinstance(message, str):
        stripped = message.strip()
        return stripped or None
    return None


def _append_message_to_session(session: Dict[str, Any], message: Optional[Union[str, List[str]]]):
    message_content = _normalize_message_content(message)
    if message_content:
        session.setdefault("messages", []).append({"role": "user", "content": message_content})


def _group_step_ids_by_requirement(plan: Any) -> Dict[str, List[str]]:
    grouped: Dict[str, List[str]] = {}
    if not isinstance(plan, list):
        return grouped
    for step in plan:
        if not isinstance(step, dict):
            continue
        step_id = str(step.get("id", ""))
        if "-S" not in step_id:
            continue
        requirement_id = step_id.split("-S", 1)[0]
        if not requirement_id:
            continue
        grouped.setdefault(requirement_id, []).append(step_id)
    for requirement_id in grouped:
        grouped[requirement_id] = sorted(grouped[requirement_id])
    return grouped


def _rebuild_requirement_step_ids(session: Dict[str, Any]):
    requirements = session.get("requirements")
    plan = session.get("plan")
    if not isinstance(requirements, list) or not isinstance(plan, list):
        return
    grouped = _group_step_ids_by_requirement(plan)
    rebuilt: List[Dict[str, Any]] = []
    for req in _normalize_requirements(requirements):
        req["step_ids"] = grouped.get(req.get("id", ""), [])
        rebuilt.append(req)
    session["requirements"] = rebuilt


def _apply_incoming_plan(session: Dict[str, Any], plan: Optional[List[Dict[str, Any]]], *, rebuild_requirements: bool = False):
    if plan is None:
        return
    session["plan"] = _normalize_plan(plan)
    if rebuild_requirements:
        _rebuild_requirement_step_ids(session)


def _apply_state_to_session(session: Dict[str, Any], state: AgentState):
    state_dict = _to_plain(state)
    session["messages"] = list(state_dict.get("messages", []))[-12:]
    session["current_agent"] = state_dict.get("current_agent", session.get("current_agent", NextNode.CHAT))
    session["mode"] = state_dict.get("mode", session.get("mode", Mode.CHAT))
    session["next_node"] = state_dict.get("next_node", session.get("next_node", NextNode.CHAT))
    session["plan"] = _normalize_plan(state_dict.get("plan", session.get("plan")))
    session["requirements"] = _normalize_requirements(state_dict.get("requirements", session.get("requirements", [])))
    session["current_step"] = state_dict.get("current_step", session.get("current_step", 0))
    session["current_step_id"] = state_dict.get("current_step_id", session.get("current_step_id"))
    session["current_step_title"] = state_dict.get("current_step_title", session.get("current_step_title"))
    session["mailbox"] = state_dict.get("mailbox", session.get("mailbox", []))
    session["ready_for_plan"] = bool(state_dict.get("ready_for_plan", False))
    session["suggested_actions"] = state_dict.get("suggested_actions", [])
    session["last_failed_node"] = state_dict.get("last_failed_node")
    session["last_error_message"] = state_dict.get("last_error_message")
    session["retry_count"] = int(state_dict.get("retry_count", 0) or 0)
    session["max_node_retries"] = int(state_dict.get("max_node_retries", session.get("max_node_retries", 1)) or 1)
    session["retrying_node"] = state_dict.get("retrying_node")
    session["progress_text"] = state_dict.get("progress_text")
    session["last_action_summary"] = state_dict.get("last_action_summary")
    session["last_validation_summary"] = state_dict.get("last_validation_summary")
    session["last_validation_status"] = state_dict.get("last_validation_status")
    session["last_validation_passed"] = state_dict.get("last_validation_passed")
    session["last_failure_category"] = state_dict.get("last_failure_category")
    session["last_evidence"] = state_dict.get("last_evidence", [])
    session["last_outcome"] = state_dict.get("last_outcome")
    session["goal"] = state_dict.get("goal", session.get("goal"))
    session["plan_status"] = state_dict.get("plan_status", session.get("plan_status", PlanStatus.DRAFT))
    session["run_id"] = state_dict.get("run_id", session.get("run_id"))
    session["run_status"] = state_dict.get("run_status", session.get("run_status", RunStatus.IDLE))
    session["approval_required"] = bool(state_dict.get("approval_required", False))
    session["approval_type"] = state_dict.get("approval_type")
    session["approval_payload"] = state_dict.get("approval_payload")
    session["pending_approvals"] = state_dict.get("pending_approvals", session.get("pending_approvals", []))
    session["risk_actions"] = state_dict.get("risk_actions", session.get("risk_actions", []))
    session["run_summary"] = state_dict.get("run_summary", session.get("run_summary"))
    session["workspace_root"] = state_dict.get("workspace_root", session.get("workspace_root"))
    session["tool_events"] = state_dict.get("tool_events", session.get("tool_events", []))
    session["last_tool_event"] = state_dict.get("last_tool_event", session.get("last_tool_event"))
    session["last_saved_at"] = state_dict.get("last_saved_at", session.get("last_saved_at"))
    session["last_restored_at"] = state_dict.get("last_restored_at", session.get("last_restored_at"))
    session["persisted_file"] = state_dict.get("persisted_file", session.get("persisted_file"))
    session["restored_from_disk"] = bool(state_dict.get("restored_from_disk", session.get("restored_from_disk", False)))
    session["updated_at"] = state_dict.get("updated_at", session.get("updated_at"))


def _persist_and_respond(session_id: str, session: Dict[str, Any], workspace_root: Optional[str]) -> Dict[str, Any]:
    response_state = _session_to_state(session_id, session)
    response_state.workspace_root = workspace_root
    export_requirements_snapshot(_normalize_requirements(session.get("requirements", [])))
    save_state(response_state)
    save_session_state(response_state)
    _hydrate_session_cache(response_state)
    return _build_state_response(response_state)


def _resolve_approval_for_session(
    session_id: str,
    session: Dict[str, Any],
    resolution_request: ApprovalResolutionRequest,
    workspace_root: Optional[str],
) -> Dict[str, Any]:
    print(
        f"[Approval] Resolving approval session={session_id} approval_id={resolution_request.approval_id} "
        f"decision={resolution_request.decision}"
    )
    current_state = _load_session_state(session_id) or _build_state_from_session(session_id, session)
    try:
        resolution = ApprovalResolution(
            approval_id=resolution_request.approval_id,
            decision=ApprovalDecision(resolution_request.decision),
            note=resolution_request.note,
        )
        current_state = resolve_approval(current_state, resolution)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    _apply_state_to_session(session, current_state)

    resolved_workspace_root = workspace_root or current_state.workspace_root
    should_continue_graph = (
        resolution.decision == ApprovalDecision.APPROVED
        and current_state.mode == Mode.EXECUTING
        and current_state.run_status == RunStatus.RUNNING
        and not current_state.approval_required
    )

    if should_continue_graph:
        print(
            f"[Approval] Approval approved; continuing execution graph for session={session_id} "
            f"mode={current_state.mode} run_status={current_state.run_status}"
        )
        return _graph_invoke_for_session(
            session_id,
            session,
            resolved_workspace_root,
            mode=current_state.mode,
            trigger_plan=False,
            interface_refresh=False,
            next_node=current_state.next_node or NextNode.CHAT,
        )

    print(
        f"[Approval] Approval resolved without graph continuation for session={session_id} "
        f"mode={current_state.mode} run_status={current_state.run_status} "
        f"approval_required={current_state.approval_required}"
    )
    return _persist_and_respond(session_id, session, workspace_root)


def _consume_last_user_action(session: Dict[str, Any], last_user_action: Optional[UserAction]) -> Optional[UserAction]:
    effective_last_user_action = last_user_action
    if last_user_action is None:
        session["consumed_last_user_action"] = None
    elif session.get("consumed_last_user_action") == last_user_action:
        effective_last_user_action = None
    else:
        session["consumed_last_user_action"] = last_user_action
    return effective_last_user_action


def _apply_user_action_to_session(
    session_id: str,
    session: Dict[str, Any],
    workspace_root: Optional[str],
    effective_last_user_action: Optional[UserAction],
    *,
    interface_refresh: bool,
    next_node: Optional[NextNode],
) -> tuple[Mode, bool, NextNode]:
    if not effective_last_user_action:
        return session.get("mode", Mode.CHAT), False, next_node or NextNode.CHAT

    gate_state = _load_session_state(session_id) or _build_state_from_session(session_id, session)
    policy_result = evaluate_action(gate_state, effective_last_user_action)
    if policy_result.decision != PolicyDecision.APPLY:
        raise HTTPException(
            status_code=409,
            detail={
                "gated": True,
                "reason": policy_result.reason,
                **_build_state_response(gate_state),
            },
        )

    session_state = AgentState(
        session_id=session_id,
        messages=session.get("messages", []),
        workspace_root=workspace_root,
        plan=session.get("plan"),
        requirements=_normalize_requirements(session.get("requirements", [])),
        current_step=session.get("current_step", 0),
        current_step_id=session.get("current_step_id"),
        current_step_title=session.get("current_step_title"),
        mailbox=session.get("mailbox", []),
        current_agent=session.get("current_agent", NextNode.CHAT),
        mode=session.get("mode", Mode.CHAT),
        trigger_plan=False,
        interface_refresh=interface_refresh,
        last_user_action=None,
        next_node=next_node or NextNode.CHAT,
        tool_call=None,
        tool_events=session.get("tool_events", []),
        last_tool_event=session.get("last_tool_event"),
        iterations=0,
        max_iterations=5,
        ready_for_plan=bool(session.get("ready_for_plan", False)),
        suggested_actions=session.get("suggested_actions", []),
        last_failed_node=session.get("last_failed_node"),
        last_error_message=session.get("last_error_message"),
        retry_count=int(session.get("retry_count", 0) or 0),
        max_node_retries=int(session.get("max_node_retries", 1) or 1),
        retrying_node=session.get("retrying_node"),
        progress_text=session.get("progress_text"),
        last_action_summary=session.get("last_action_summary"),
        last_validation_summary=session.get("last_validation_summary"),
        last_validation_status=session.get("last_validation_status"),
        last_validation_passed=session.get("last_validation_passed"),
        last_failure_category=session.get("last_failure_category"),
        last_evidence=session.get("last_evidence", []),
        last_outcome=session.get("last_outcome"),
        goal=session.get("goal"),
        plan_status=session.get("plan_status", PlanStatus.DRAFT),
        run_id=session.get("run_id"),
        run_status=session.get("run_status", RunStatus.IDLE),
        approval_required=bool(session.get("approval_required", False)),
        approval_type=session.get("approval_type"),
        approval_payload=session.get("approval_payload"),
        pending_approvals=session.get("pending_approvals", []),
        risk_actions=session.get("risk_actions", []),
        run_summary=session.get("run_summary"),
        last_saved_at=session.get("last_saved_at"),
        last_restored_at=session.get("last_restored_at"),
        persisted_file=session.get("persisted_file"),
        restored_from_disk=bool(session.get("restored_from_disk", False)),
        updated_at=session.get("updated_at"),
    )
    session_state = handle_user_action(effective_last_user_action, session_state)
    _apply_state_to_session(session, session_state)
    return session_state.mode, session_state.trigger_plan, session_state.next_node or NextNode.CHAT


def _graph_invoke_for_session(
    session_id: str,
    session: Dict[str, Any],
    workspace_root: Optional[str],
    *,
    mode: Mode,
    trigger_plan: bool,
    interface_refresh: bool,
    next_node: Optional[NextNode],
) -> Dict[str, Any]:
    state = AgentState(
        session_id=session_id,
        messages=session.get("messages", []),
        workspace_root=workspace_root,
        plan=session.get("plan"),
        requirements=_normalize_requirements(session.get("requirements", [])),
        current_step=session.get("current_step", 0),
        current_step_id=session.get("current_step_id"),
        current_step_title=session.get("current_step_title"),
        mailbox=session.get("mailbox", []),
        current_agent=session.get("current_agent", NextNode.CHAT),
        mode=mode,
        trigger_plan=trigger_plan,
        interface_refresh=interface_refresh,
        last_user_action=None,
        next_node=next_node or NextNode.CHAT,
        tool_call=None,
        tool_events=session.get("tool_events", []),
        last_tool_event=session.get("last_tool_event"),
        iterations=0,
        max_iterations=5,
        ready_for_plan=bool(session.get("ready_for_plan", False)),
        suggested_actions=session.get("suggested_actions", []),
        last_failed_node=session.get("last_failed_node"),
        last_error_message=session.get("last_error_message"),
        retry_count=int(session.get("retry_count", 0) or 0),
        max_node_retries=int(session.get("max_node_retries", 1) or 1),
        retrying_node=session.get("retrying_node"),
        progress_text=session.get("progress_text"),
        last_action_summary=session.get("last_action_summary"),
        last_validation_summary=session.get("last_validation_summary"),
        last_validation_status=session.get("last_validation_status"),
        last_validation_passed=session.get("last_validation_passed"),
        last_failure_category=session.get("last_failure_category"),
        last_evidence=session.get("last_evidence", []),
        last_outcome=session.get("last_outcome"),
        goal=session.get("goal"),
        plan_status=session.get("plan_status", PlanStatus.DRAFT),
        run_id=session.get("run_id"),
        run_status=session.get("run_status", RunStatus.IDLE),
        approval_required=bool(session.get("approval_required", False)),
        approval_type=session.get("approval_type"),
        approval_payload=session.get("approval_payload"),
        pending_approvals=session.get("pending_approvals", []),
        risk_actions=session.get("risk_actions", []),
        run_summary=session.get("run_summary"),
        last_saved_at=session.get("last_saved_at"),
        last_restored_at=session.get("last_restored_at"),
        persisted_file=session.get("persisted_file"),
        restored_from_disk=bool(session.get("restored_from_disk", False)),
        updated_at=session.get("updated_at"),
    )

    recursion_limit = 20 if session.get("mode") == "executing" or mode == Mode.EXECUTING else 5
    result = graph.invoke(state, config={"recursion_limit": recursion_limit})
    result_state = result if isinstance(result, AgentState) else AgentState.model_validate(result)
    _apply_state_to_session(session, result_state)
    return _persist_and_respond(session_id, session, workspace_root)


def _run_request(
    *,
    session_id: str,
    workspace_root: Optional[str],
    message: Optional[Union[str, List[str]]] = None,
    plan: Optional[List[Dict[str, Any]]] = None,
    last_user_action: Optional[UserAction] = None,
    mode: Mode = Mode.CHAT,
    trigger_plan: bool = False,
    interface_refresh: bool = False,
    next_node: Optional[NextNode] = None,
    approval_resolution: Optional[ApprovalResolutionRequest] = None,
    require_workspace: bool = True,
    rebuild_requirements: bool = False,
    skip_graph: bool = False,
    dedupe_action: bool = True,
) -> Dict[str, Any]:
    session = _get_or_create_session(session_id)
    resolved_workspace_root = _resolve_workspace_root(session, workspace_root, required=require_workspace)
    _append_message_to_session(session, message)
    _apply_incoming_plan(session, plan, rebuild_requirements=rebuild_requirements)

    if approval_resolution is not None:
        return _resolve_approval_for_session(
            session_id,
            session,
            approval_resolution,
            resolved_workspace_root,
        )

    effective_last_user_action = last_user_action
    if dedupe_action:
        effective_last_user_action = _consume_last_user_action(session, last_user_action)

    try:
        req_mode, req_trigger_plan, req_next_node = _apply_user_action_to_session(
            session_id,
            session,
            resolved_workspace_root,
            effective_last_user_action,
            interface_refresh=interface_refresh,
            next_node=next_node,
        )
    except HTTPException as exc:
        if exc.status_code == 409 and isinstance(exc.detail, dict) and exc.detail.get("gated"):
            return exc.detail
        raise

    if not effective_last_user_action:
        req_mode = session.get("mode", mode)
        req_trigger_plan = trigger_plan
        req_next_node = next_node or NextNode.CHAT

    if skip_graph:
        return _persist_and_respond(session_id, session, resolved_workspace_root)

    return _graph_invoke_for_session(
        session_id,
        session,
        resolved_workspace_root,
        mode=req_mode,
        trigger_plan=req_trigger_plan,
        interface_refresh=interface_refresh,
        next_node=req_next_node,
    )


@app.get("/")
def health():
    return {"status": "Agent running"}


@app.get("/state")
def get_state(session_id: Optional[str] = None):
    state = _load_session_state(session_id)
    if state is None:
        state = _load_persisted_state()
    if state is None:
        raise HTTPException(status_code=404, detail="No saved state available")

    return _build_state_response(state)


@app.post("/state/reload")
def reload_state(req: ReloadStateRequest):
    state = load_session_state(AgentState, req.session_id)
    if state is None:
        state = _load_session_state(req.session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="No saved state available for session")
    _hydrate_session_cache(state)
    response = _build_state_response(state)
    response["reload_source"] = "disk" if state.restored_from_disk else "memory"
    return response


@app.post("/state/reset")
def reset_state(req: ResetStateRequest):
    """Reset a session to an empty state (no plan, no requirements)."""
    session = _empty_session()
    conversations[req.session_id] = session
    state = _session_to_state(req.session_id, session)
    save_state(state)
    save_session_state(state)
    _hydrate_session_cache(state)
    response = _build_state_response(state)
    response["reset"] = True
    return response


@app.get("/state/summary")
def get_state_summary(session_id: str):
    state = _load_session_state(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="No saved state available for session")
    response = _build_state_response(state)
    return {
        "session_id": response.get("session_id"),
        "current_step": response.get("current_step"),
        "current_step_id": response.get("current_step_id"),
        "current_step_title": response.get("current_step_title"),
        "current_agent": response.get("current_agent"),
        "progress_text": response.get("progress_text"),
        "last_error_message": response.get("last_error_message"),
        "retrying_node": response.get("retrying_node"),
        "mode": response.get("mode"),
        "run_status": response.get("run_status"),
        "execution": response.get("execution"),
        "persistence": response.get("persistence"),
        "last_tool_event": response.get("last_tool_event"),
        "tool_events_count": len(response.get("tool_events") or []),
    }


@app.get("/state/tool-events")
def get_tool_events(session_id: str):
    state = _load_session_state(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="No saved state available for session")
    response = _build_state_response(state)
    tool_events = response.get("tool_events") or []
    return {
        "session_id": response.get("session_id"),
        "tool_events": tool_events,
        "count": len(tool_events),
        "last_tool_event": response.get("last_tool_event"),
    }


@app.post("/test/mark-step")
def mark_step(req: MarkStepRequest):
    state = _load_session_state(req.session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="No saved state available for session")
    if not state.plan:
        raise HTTPException(status_code=400, detail="No plan is available for this session")

    status_map = {
        "pending": StepStatus.PENDING,
        "running": StepStatus.RUNNING,
        "done": StepStatus.SUCCESS,
        "failed": StepStatus.FAILED,
        "success": StepStatus.SUCCESS,
    }
    mapped_status = status_map.get(req.status)
    if mapped_status is None:
        raise HTTPException(status_code=400, detail="status must be one of: pending, running, done, failed")

    updated = False
    new_plan = []
    for step in state.plan:
        if step.id == req.step_id:
            new_plan.append(step.model_copy(update={"status": mapped_status}))
            updated = True
        else:
            new_plan.append(step)

    if not updated:
        raise HTTPException(status_code=404, detail=f"Step not found: {req.step_id}")

    state.plan = new_plan
    state.run_summary = None
    save_state(state)
    save_session_state(state)
    _hydrate_session_cache(state)
    return _build_state_response(state)


@app.post("/plan/generate")
def generate_plan(req: PlanGenerateRequest):
    return _run_request(
        session_id=req.session_id,
        workspace_root=req.workspace_root,
        plan=req.plan,
        last_user_action=UserAction.GENERATE_PLAN,
        require_workspace=True,
    )


@app.post("/plan/modify")
def modify_plan(req: PlanModifyRequest):
    instruction = req.instruction.strip()
    if not instruction:
        raise HTTPException(status_code=400, detail="instruction is required")
    return _run_request(
        session_id=req.session_id,
        workspace_root=req.workspace_root,
        message=instruction,
        plan=req.plan,
        last_user_action=UserAction.MODIFY_PLAN,
        require_workspace=True,
    )


@app.post("/plan/save")
def save_plan(req: PlanSaveRequest):
    return _run_request(
        session_id=req.session_id,
        workspace_root=req.workspace_root,
        plan=req.plan,
        last_user_action=UserAction.SAVE_PLAN,
        require_workspace=True,
        rebuild_requirements=True,
        skip_graph=True,
        dedupe_action=False,
    )


@app.post("/plan/execute")
def execute_plan(req: PlanExecuteRequest):
    return _run_request(
        session_id=req.session_id,
        workspace_root=req.workspace_root,
        plan=req.plan,
        last_user_action=UserAction.EXECUTE_PLAN,
        require_workspace=True,
        dedupe_action=False,
    )


@app.post("/approval/resolve")
def approval_resolve(req: ApprovalResolveRequest):
    return _run_request(
        session_id=req.session_id,
        workspace_root=None,
        approval_resolution=ApprovalResolutionRequest(
            approval_id=req.approval_id,
            decision=req.decision,
            note=req.note,
        ),
        require_workspace=False,
        skip_graph=True,
        dedupe_action=False,
    )


@app.post("/chat")
def chat(req: ChatRequest):
    return _run_request(
        session_id=req.session_id,
        workspace_root=req.workspace_root,
        message=req.message,
        plan=req.plan,
        last_user_action=req.last_user_action,
        mode=req.mode,
        trigger_plan=req.trigger_plan,
        interface_refresh=req.interface_refresh,
        next_node=req.next_node,
        approval_resolution=req.approval_resolution,
        require_workspace=True,
    )
