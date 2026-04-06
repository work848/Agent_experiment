import json
import os
from typing import Any

from datetime import datetime, timezone


def _apply_save_metadata(state: Any, filepath: str):
    timestamp = datetime.now(timezone.utc).isoformat()
    state.last_saved_at = timestamp
    state.updated_at = timestamp
    state.persisted_file = filepath


def save_session_state(state: Any):
    session_id = state.session_id
    path = f"src/memory/state/sessions/{session_id}.json"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    _apply_save_metadata(state, path)
    state_dict = state.model_dump(mode="json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state_dict, f, indent=2, ensure_ascii=False)
    print(f"[Checkpoint] Session state saved -> {path}")


def save_state(state: Any, filepath="src/memory/state/current_state.json"):
    """
    保存整个 AgentState
    """

    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    _apply_save_metadata(state, filepath)

    # mode="json" 保证嵌套模型可序列化
    state_dict = state.model_dump(mode="json")

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(state_dict, f, indent=2, ensure_ascii=False)

    print(f"[Checkpoint] State saved -> {filepath}")