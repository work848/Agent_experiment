from pathlib import Path

WORKSPACE = Path("workspace").resolve()


def safe_path(path: str):

    full_path = (WORKSPACE / path).resolve()

    if not str(full_path).startswith(str(WORKSPACE)):
        raise ValueError("Path outside workspace")

    return full_path