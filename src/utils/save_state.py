import json
import os
from typing import Any

from datetime import datetime

def save_state_versioned(state):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = f"src/memory/state/state_{ts}.json"
    save_state(state, path)


def save_state(state: Any, filepath="src/memory/state/current_state.json"):
    """
    保存整个 AgentState（安全版本）
    """

    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    # mode="json" 保证嵌套模型可序列化
    state_dict = state.model_dump(mode="json")

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(state_dict, f, indent=2, ensure_ascii=False)

    print(f"[Checkpoint] State saved → {filepath}")