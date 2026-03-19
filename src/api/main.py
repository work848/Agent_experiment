import os
from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field
from agent.state import AgentState, Mode, UserAction, NextNode, Step,Email
from typing import Optional, List, Dict
from agent.graph.build_graph import build_graph

load_dotenv(dotenv_path="APIKey.env")

app = FastAPI()

graph = build_graph()

# session memory
conversations = {}
class ChatRequest(BaseModel):
    session_id: str
    message: list[str]
    trigger_plan: bool = False
    interface_refresh: bool = False
    
    last_user_action: Optional[UserAction] = None
    next_node: Optional[NextNode] = None
    mode: Mode.CHAT = Mode.CHAT
    


@app.get("/")
def health():
    return {"status": "Agent running"}


@app.post("/chat")
def chat(req: ChatRequest):

    # ===== 获取 session =====
    session = conversations.setdefault(
        req.session_id,
        {
            "messages": [],
            "mode": Mode.CHAT
        }
    )

    # ===== 保存 user message =====
    session["messages"].append({
        "role": "user",
        "content": req.message
    })

    # ===== 构建 graph state =====
    state = AgentState(
        session_id=req.session_id,
        messages=session["messages"],

        workspace_root=None,
        plan=None,
        current_step=0,
        mailbox=[],

        mode = Mode.CHAT,
        tool_call=None,

        iterations=0,
        max_iterations=5
    )
    # ===== 调用 agent =====
    result = graph.invoke(state)

    # ===== conversation window =====
    session["messages"] = result["messages"][-12:]

    return state