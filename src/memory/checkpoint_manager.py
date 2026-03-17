import os
import json

CHECKPOINT_DIR = "memory/checkpoints"


def save_checkpoint(session_id, state):

    os.makedirs(CHECKPOINT_DIR, exist_ok=True)

    path = f"{CHECKPOINT_DIR}/{session_id}.json"

    with open(path, "w") as f:
        json.dump(state, f, indent=2)


def load_checkpoint(session_id):

    path = f"{CHECKPOINT_DIR}/{session_id}.json"

    if not os.path.exists(path):
        return None

    with open(path) as f:
        return json.load(f)