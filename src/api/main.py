import os
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent.graph.build_graph import build_graph
from agent.state import (
    AgentState, Mode, NextNode, PlanStatus, RunStatus, ApprovalType, UserAction,
)
from utils.requirements_export import export_requirements_snapshot
from utils.user_action import handle_user_action
from utils.save_state import save_state, save_session_state
from utils.restore_state import load_state, load_latest_state, load_session_state
from utils.action_policy import evaluate_action, PolicyDecision
from utils.approval_flow import ApprovalResolution, ApprovalDecision, resolve_approval

load_dotenv(dotenv_path="APIKey.env")
load_dotenv(dotenv_path="WORKSPACE_ROOT.env")
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
        status = step_dict.get("status")
        if status == "success":
            step_dict["status"] = "done"
        elif status in {"pending", "running", "failed", "done"}:
            step_dict["status"] = status
        else:
            step_dict["status"] = "pending"
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


def _build_state_response(state: AgentState) -> Dict[str, Any]:
    plan = _normalize_plan(getattr(state, "plan", []))
    requirements = _normalize_requirements(getattr(state, "requirements", []))
    return {
        "plan": plan,
        "requirements": requirements,
        "current_step": int(getattr(state, "current_step", 0) or 0),
        "current_step_id": getattr(state, "current_step_id", None),
        "current_step_title": getattr(state, "current_step_title", None),
        "agents": _derive_agents({"current_agent": getattr(state, "current_agent", NextNode.CHAT)}),
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
        mode=session.get("mode", Mode.CHAT),
        trigger_plan=False,
        interface_refresh=False,
        last_user_action=None,
        next_node=session.get("next_node", NextNode.CHAT),
        tool_call=None,
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
    )


def _load_session_state(session_id: Optional[str]) -> Optional[AgentState]:
    if not session_id:
        return None
    # Try durable session-scoped file first
    state = load_session_state(AgentState, session_id)
    if state is not None:
        return state
    # Fall back to in-process cache
    session = conversations.get(session_id)
    if not session:
        return None
    return _session_to_state(session_id, session)


def _load_persisted_state() -> Optional[AgentState]:
    state = load_state(AgentState)
    if state is not None:
        return state
    return load_latest_state(AgentState)
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


@app.post("/chat")
def chat(req: ChatRequest):
    session = conversations.setdefault(
        req.session_id,
        {
            "messages": [],
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
        },
    )

    resolved_workspace_root = req.workspace_root or session.get("workspace_root") or os.getenv("WORKSPACE_ROOT")
    if not resolved_workspace_root:
        raise HTTPException(status_code=400, detail="workspace_root is required. Pass it in the payload or set WORKSPACE_ROOT env variable.")
    session["workspace_root"] = resolved_workspace_root

    message_content: Optional[str] = None
    if isinstance(req.message, list):
        message_content = "\n".join(str(x) for x in req.message)
    elif isinstance(req.message, str):
        message_content = req.message

    if message_content and message_content.strip():
        session["messages"].append({"role": "user", "content": message_content})

    # 前端手动编辑后的 plan/interface 覆盖会话内计划
    if req.plan is not None:
        session["plan"] = req.plan

    # --- approval resolution: early-return path, skip graph ---
    if req.approval_resolution is not None:
        ar = req.approval_resolution
        current_state = _load_session_state(req.session_id) or _session_to_state(req.session_id, session)
        try:
            resolution = ApprovalResolution(
                approval_id=ar.approval_id,
                decision=ApprovalDecision(ar.decision),
                note=ar.note,
            )
            current_state = resolve_approval(current_state, resolution)
        except (ValueError, KeyError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        session["run_status"] = _to_plain(current_state.run_status)
        session["mode"] = _to_plain(current_state.mode)
        session["approval_required"] = current_state.approval_required
        session["approval_type"] = _to_plain(current_state.approval_type)
        session["approval_payload"] = current_state.approval_payload
        session["pending_approvals"] = _to_plain(current_state.pending_approvals)
        save_session_state(current_state)
        return _build_state_response(current_state)

    # last_user_action 按”边沿触发”处理，避免前端重复传同一值造成重复执行
    effective_last_user_action = req.last_user_action
    if req.last_user_action is None:
        session["consumed_last_user_action"] = None
    elif session.get("consumed_last_user_action") == req.last_user_action:
        effective_last_user_action = None
    else:
        session["consumed_last_user_action"] = req.last_user_action

    # 在进入图前先处理会话级用户动作，避免依赖图内多轮路由导致递归超限
    if effective_last_user_action:
        # Policy gate: check if action is allowed given current state
        _gate_state = _load_session_state(req.session_id) or _session_to_state(req.session_id, session)
        policy_result = evaluate_action(_gate_state, effective_last_user_action)
        if policy_result.decision != PolicyDecision.APPLY:
            return {
                "gated": True,
                "reason": policy_result.reason,
                **_build_state_response(_gate_state),
            }
        session_state = AgentState(
            session_id=req.session_id,
            messages=session.get("messages", []),
            workspace_root=resolved_workspace_root,
            plan=session.get("plan"),
            requirements=_normalize_requirements(session.get("requirements", [])),
            current_step=session.get("current_step", 0),
            current_step_id=session.get("current_step_id"),
            current_step_title=session.get("current_step_title"),
            mailbox=session.get("mailbox", []),
            mode=session.get("mode", Mode.CHAT),
            trigger_plan=False,
            interface_refresh=req.interface_refresh,
            last_user_action=None,
            next_node=req.next_node or NextNode.CHAT,
            tool_call=None,
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
            last_validation_passed=session.get("last_validation_passed"),
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
        )
        session_state = handle_user_action(effective_last_user_action, session_state)
        session["mode"] = session_state.mode
        session["current_step"] = session_state.current_step
        session["current_step_id"] = session_state.current_step_id
        session["current_step_title"] = session_state.current_step_title
        session["last_error_message"] = session_state.last_error_message
        session["retry_count"] = session_state.retry_count
        session["retrying_node"] = session_state.retrying_node
        session["progress_text"] = session_state.progress_text
        session["last_action_summary"] = session_state.last_action_summary
        session["last_validation_summary"] = session_state.last_validation_summary
        session["last_validation_status"] = _to_plain(session_state.last_validation_status)
        session["last_validation_passed"] = session_state.last_validation_passed
        session["last_failure_category"] = _to_plain(session_state.last_failure_category)
        session["last_evidence"] = _to_plain(session_state.last_evidence)
        session["last_outcome"] = _to_plain(session_state.last_outcome)
        session["goal"] = _to_plain(session_state.goal)
        session["plan_status"] = _to_plain(session_state.plan_status)
        session["run_id"] = session_state.run_id
        session["run_status"] = _to_plain(session_state.run_status)
        session["approval_required"] = session_state.approval_required
        session["approval_type"] = _to_plain(session_state.approval_type)
        session["approval_payload"] = _to_plain(session_state.approval_payload)
        session["pending_approvals"] = _to_plain(session_state.pending_approvals)
        session["risk_actions"] = _to_plain(session_state.risk_actions)
        req_mode = session_state.mode
        req_trigger_plan = session_state.trigger_plan
        req_next_node = session_state.next_node or NextNode.CHAT
    else:
        req_mode = session.get("mode", req.mode)
        req_trigger_plan = req.trigger_plan
        req_next_node = req.next_node or NextNode.CHAT

    state = AgentState(
        session_id=req.session_id,
        messages=session.get("messages", []),
        workspace_root=resolved_workspace_root,
        plan=session.get("plan"),
        requirements=_normalize_requirements(session.get("requirements", [])),
        current_step=session.get("current_step", 0),
        current_step_id=session.get("current_step_id"),
        current_step_title=session.get("current_step_title"),
        mailbox=session.get("mailbox", []),
        mode=req_mode,
        trigger_plan=req_trigger_plan,
        interface_refresh=req.interface_refresh,
        last_user_action=None,
        next_node=req_next_node,
        tool_call=None,
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
    )

    recursion_limit = 20 if session.get("mode") == "executing" else 5
    result = graph.invoke(state, config={"recursion_limit": recursion_limit})
    result_dict = _to_plain(result)

    session["messages"] = (result_dict.get("messages") or session["messages"])[-12:]
    session["mode"] = result_dict.get("mode", req_mode)
    session["plan"] = result_dict.get("plan", session.get("plan"))
    session["requirements"] = _normalize_requirements(result_dict.get("requirements", session.get("requirements", [])))
    session["current_step"] = result_dict.get("current_step", session.get("current_step", 0))
    session["current_step_id"] = result_dict.get("current_step_id", session.get("current_step_id"))
    session["current_step_title"] = result_dict.get("current_step_title", session.get("current_step_title"))
    session["mailbox"] = result_dict.get("mailbox", session.get("mailbox", []))
    session["ready_for_plan"] = bool(result_dict.get("ready_for_plan", False))
    session["suggested_actions"] = result_dict.get("suggested_actions", [])
    session["last_failed_node"] = result_dict.get("last_failed_node")
    session["last_error_message"] = result_dict.get("last_error_message")
    session["retry_count"] = int(result_dict.get("retry_count", 0) or 0)
    session["max_node_retries"] = int(result_dict.get("max_node_retries", session.get("max_node_retries", 1)) or 1)
    session["retrying_node"] = result_dict.get("retrying_node")
    session["progress_text"] = result_dict.get("progress_text")
    session["last_action_summary"] = result_dict.get("last_action_summary")
    session["last_validation_summary"] = result_dict.get("last_validation_summary")
    session["last_validation_status"] = result_dict.get("last_validation_status")
    session["last_validation_passed"] = result_dict.get("last_validation_passed")
    session["last_failure_category"] = result_dict.get("last_failure_category")
    session["last_evidence"] = result_dict.get("last_evidence", [])
    session["last_outcome"] = result_dict.get("last_outcome")
    # --- product-state fields ---
    session["goal"] = result_dict.get("goal", session.get("goal"))
    session["plan_status"] = result_dict.get("plan_status", session.get("plan_status", PlanStatus.DRAFT))
    session["run_id"] = result_dict.get("run_id", session.get("run_id"))
    session["run_status"] = result_dict.get("run_status", session.get("run_status", RunStatus.IDLE))
    session["approval_required"] = bool(result_dict.get("approval_required", False))
    session["approval_type"] = result_dict.get("approval_type")
    session["approval_payload"] = result_dict.get("approval_payload")
    session["pending_approvals"] = result_dict.get("pending_approvals", session.get("pending_approvals", []))
    session["risk_actions"] = result_dict.get("risk_actions", session.get("risk_actions", []))
    session["run_summary"] = result_dict.get("run_summary", session.get("run_summary"))

    response = {
        "plan": _normalize_plan(result_dict.get("plan", session.get("plan"))),
        "requirements": _normalize_requirements(result_dict.get("requirements", session.get("requirements", []))),
        "current_step": int(result_dict.get("current_step", session.get("current_step", 0)) or 0),
        "current_step_id": session.get("current_step_id"),
        "current_step_title": session.get("current_step_title"),
        "agents": _derive_agents(result_dict),
        "logs": _derive_logs(result_dict),
        "messages": result_dict.get("messages", session["messages"]),
        "ready_for_plan": session.get("ready_for_plan", False),
        "actions": session.get("suggested_actions", []),
        "last_error_message": session.get("last_error_message"),
        "retry_count": int(session.get("retry_count", 0) or 0),
        "retrying_node": session.get("retrying_node"),
        "progress_text": session.get("progress_text"),
        "last_action_summary": session.get("last_action_summary"),
        "last_validation_summary": session.get("last_validation_summary"),
        "last_validation_status": _to_plain(session.get("last_validation_status")),
        "last_validation_passed": session.get("last_validation_passed"),
        "last_failure_category": _to_plain(session.get("last_failure_category")),
        "last_evidence": _to_plain(session.get("last_evidence", [])),
        "last_outcome": _to_plain(session.get("last_outcome")),
        # --- product-state fields ---
        "goal": _to_plain(session.get("goal")),
        "plan_status": _to_plain(session.get("plan_status", PlanStatus.DRAFT)),
        "run_status": _to_plain(session.get("run_status", RunStatus.IDLE)),
        "approval_required": bool(session.get("approval_required", False)),
        "approval_type": _to_plain(session.get("approval_type")),
        "approval_payload": session.get("approval_payload"),
        "pending_approvals": _to_plain(session.get("pending_approvals", [])),
        "risk_actions": _to_plain(session.get("risk_actions", [])),
        "run_summary": session.get("run_summary"),
    }

    export_requirements_snapshot(_normalize_requirements(session.get("requirements", [])))

    # 将当前完整状态落盘，供前端/后续流程复用
    save_state(
        AgentState(
            session_id=req.session_id,
            messages=session.get("messages", []),
            workspace_root=resolved_workspace_root,
            plan=session.get("plan"),
            requirements=_normalize_requirements(session.get("requirements", [])),
            current_step=session.get("current_step", 0),
            current_step_id=session.get("current_step_id"),
            current_step_title=session.get("current_step_title"),
            mailbox=session.get("mailbox", []),
            mode=session.get("mode", Mode.CHAT),
            trigger_plan=bool(result_dict.get("trigger_plan", False)),
            interface_refresh=bool(result_dict.get("interface_refresh", False)),
            last_user_action=None,
            next_node=result_dict.get("next_node", req_next_node),
            tool_call=None,
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
            last_validation_passed=session.get("last_validation_passed"),
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
        )
    )

    # Session-scoped durable save (canonical truth)
    save_session_state(
        AgentState(
            session_id=req.session_id,
            messages=session.get("messages", []),
            workspace_root=resolved_workspace_root,
            plan=session.get("plan"),
            requirements=_normalize_requirements(session.get("requirements", [])),
            current_step=session.get("current_step", 0),
            current_step_id=session.get("current_step_id"),
            current_step_title=session.get("current_step_title"),
            mailbox=session.get("mailbox", []),
            mode=session.get("mode", Mode.CHAT),
            trigger_plan=bool(result_dict.get("trigger_plan", False)),
            interface_refresh=bool(result_dict.get("interface_refresh", False)),
            last_user_action=None,
            next_node=result_dict.get("next_node", req_next_node),
            tool_call=None,
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
            last_validation_passed=session.get("last_validation_passed"),
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
        )
    )

    return response
