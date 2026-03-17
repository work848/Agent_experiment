import os
from tools.read_file import read_file
from config.workspace_config import WORKSPACE


def test_read_file():

    os.makedirs(WORKSPACE, exist_ok=True)

    path = f"{WORKSPACE}/sample.txt"

    with open(path, "w") as f:
        f.write("test content")

    result = read_file("sample.txt")

    assert "test content" in result