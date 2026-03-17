import os
from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel
from agent.state import AgentState
from agent.graph.build_graph import build_graph

load_dotenv(dotenv_path="APIKey.env")

app = FastAPI()

graph = build_graph()

# session memory
conversations = {}


class ChatRequest(BaseModel):

    session_id: str = "default"
    message: str
    mode: str = "coding"


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
            "mode": req.mode
        }
    )

    # ===== 保存 user message =====
    session["messages"].append({
        "role": "user",
        "content": req.message
    })

    # ===== 构建 graph state =====
    state: AgentState = {

        "messages": session["messages"],

        "tool_call": False,

        "code_context": [],

        "plan": None,

        "current_step": None,

        "retrieved_memory": [],

        "mode": req.mode
    }

    # ===== 调用 agent =====
    result = graph.invoke(state)

    # ===== conversation window =====
    session["messages"] = result["messages"][-12:]

    return {
        "response": result["messages"][-1]["content"]
    }