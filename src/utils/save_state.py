import json
import os
from typing import Any

from datetime import datetime


def save_session_state(state: Any):
    session_id = state.session_id
    path = f"src/memory/state/sessions/{session_id}.json"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    state_dict = state.model_dump(mode="json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state_dict, f, indent=2, ensure_ascii=False)
    print(f"[Checkpoint] Session state saved -> {path}")


def save_state(state: Any, filepath="src/memory/state/current_state.json"):
    """
    保存整个 AgentState
    """

    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    # mode="json" 保证嵌套模型可序列化
    state_dict = state.model_dump(mode="json")

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(state_dict, f, indent=2, ensure_ascii=False)

    print(f"[Checkpoint] State saved -> {filepath}")