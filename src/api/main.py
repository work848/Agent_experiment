import os
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent.graph.build_graph import build_graph
from agent.state import AgentState, Mode, NextNode, UserAction
from utils.requirements_export import export_requirements_snapshot
from utils.user_action import handle_user_action
from utils.save_state import save_state
from utils.restore_state import load_state, load_latest_state

load_dotenv(dotenv_path="APIKey.env")

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

    if current_agent in {"planner", "interface"}:
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
        "agents": _derive_agents({"current_agent": getattr(state, "current_agent", NextNode.CHAT)}),
        "logs": _derive_logs({"mailbox": getattr(state, "mailbox", [])}),
        "messages": list(getattr(state, "messages", []))[-12:],
        "ready_for_plan": bool(getattr(state, "ready_for_plan", False)),
        "actions": getattr(state, "suggested_actions", []),
    }


def _session_to_state(session_id: str, session: Dict[str, Any]) -> AgentState:
    return AgentState(
        session_id=session_id,
        messages=session.get("messages", []),
        workspace_root=session.get("workspace_root"),
        plan=session.get("plan"),
        requirements=_normalize_requirements(session.get("requirements", [])),
        current_step=session.get("current_step", 0),
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
    )


def _load_session_state(session_id: Optional[str]) -> Optional[AgentState]:
    if not session_id:
        return None
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
            "mailbox": [],
            "consumed_last_user_action": None,
            "ready_for_plan": False,
            "suggested_actions": [],
            "workspace_root": None,
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

    # last_user_action 按“边沿触发”处理，避免前端重复传同一值造成重复执行
    effective_last_user_action = req.last_user_action
    if req.last_user_action is None:
        session["consumed_last_user_action"] = None
    elif session.get("consumed_last_user_action") == req.last_user_action:
        effective_last_user_action = None
    else:
        session["consumed_last_user_action"] = req.last_user_action

    # 在进入图前先处理会话级用户动作，避免依赖图内多轮路由导致递归超限
    if effective_last_user_action:
        session_state = AgentState(
            session_id=req.session_id,
            messages=session.get("messages", []),
            workspace_root=resolved_workspace_root,
            plan=session.get("plan"),
            requirements=_normalize_requirements(session.get("requirements", [])),
            current_step=session.get("current_step", 0),
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
        )
        session_state = handle_user_action(effective_last_user_action, session_state)
        req_mode = session_state.mode
        req_trigger_plan = session_state.trigger_plan
        req_next_node = session_state.next_node or NextNode.CHAT
    else:
        req_mode = req.mode
        req_trigger_plan = req.trigger_plan
        req_next_node = req.next_node or NextNode.CHAT

    state = AgentState(
        session_id=req.session_id,
        messages=session.get("messages", []),
        workspace_root=resolved_workspace_root,
        plan=session.get("plan"),
        requirements=_normalize_requirements(session.get("requirements", [])),
        current_step=session.get("current_step", 0),
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
    )

    result = graph.invoke(state, config={"recursion_limit": 5})
    result_dict = _to_plain(result)

    session["messages"] = (result_dict.get("messages") or session["messages"])[-12:]
    session["mode"] = result_dict.get("mode", req_mode)
    session["plan"] = result_dict.get("plan", session.get("plan"))
    session["requirements"] = _normalize_requirements(result_dict.get("requirements", session.get("requirements", [])))
    session["current_step"] = result_dict.get("current_step", session.get("current_step", 0))
    session["mailbox"] = result_dict.get("mailbox", session.get("mailbox", []))
    session["ready_for_plan"] = bool(result_dict.get("ready_for_plan", False))
    session["suggested_actions"] = result_dict.get("suggested_actions", [])

    response = {
        "plan": _normalize_plan(result_dict.get("plan", session.get("plan"))),
        "requirements": _normalize_requirements(result_dict.get("requirements", session.get("requirements", []))),
        "current_step": int(result_dict.get("current_step", session.get("current_step", 0)) or 0),
        "agents": _derive_agents(result_dict),
        "logs": _derive_logs(result_dict),
        "messages": result_dict.get("messages", session["messages"]),
        "ready_for_plan": session.get("ready_for_plan", False),
        "actions": session.get("suggested_actions", []),
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
            mailbox=session.get("mailbox", []),
            mode=session.get("mode", Mode.CHAT),
            trigger_plan=bool(result_dict.get("trigger_plan", False)),
            interface_refresh=bool(result_dict.get("interface_refresh", False)),
            last_user_action=None,
            next_node=req_next_node,
            tool_call=None,
            iterations=0,
            max_iterations=5,
            ready_for_plan=bool(session.get("ready_for_plan", False)),
            suggested_actions=session.get("suggested_actions", []),
        )
    )

    return response
