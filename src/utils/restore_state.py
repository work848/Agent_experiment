
import json
import os
from typing import Optional

from datetime import datetime, timezone

import glob


def _apply_restore_metadata(state, filepath: str):
    state.last_restored_at = datetime.now(timezone.utc).isoformat()
    state.restored_from_disk = True
    if not getattr(state, "persisted_file", None):
        state.persisted_file = filepath
    return state

def load_session_state(state_cls, session_id: str):
    path = f"src/memory/state/sessions/{session_id}.json"
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    state = _apply_restore_metadata(state_cls.model_validate(data), path)
    print(f"[Checkpoint] Session state loaded <- {path}")
    return state


def load_latest_state(state_cls):
    files = glob.glob("src/memory/state/state_*.json")
    if not files:
        return None

    latest = max(files, key=os.path.getmtime)
    return load_state(state_cls, latest)

def load_state(state_cls, filepath="src/memory/state/current_state.json"):
    """
    从 JSON 恢复 AgentState
    """

    if not os.path.exists(filepath):
        print("[Checkpoint] No saved state found")
        return None

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 🔥 关键：Pydantic 自动重建 Step / Email
    state = _apply_restore_metadata(state_cls.model_validate(data), filepath)

    print(f"[Checkpoint] State loaded <- {filepath}")
    return state