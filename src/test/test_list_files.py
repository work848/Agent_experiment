import sys
import os
# 把 src 目录加入到搜索路径中
# sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from tools.list_files_tool import list_files
from config.workspace_config import WORKSPACE


def test_list_files():

    os.makedirs(WORKSPACE, exist_ok=True)

    with open(f"{WORKSPACE}/a.txt", "w") as f:
        f.write("hello")

    with open(f"{WORKSPACE}/b.py", "w") as f:
        f.write("print('hi')")

    result = list_files()

    assert "a.txt" in result
    assert "b.py" in result