import os
from tools.write_file_tool import write_file
from config.workspace_config import WORKSPACE


def test_write_file():

    path = "test/test_file.txt"
    content = "hello world"

    result = write_file(path, content)

    full_path = os.path.join(WORKSPACE, path)

    assert os.path.exists(full_path)

    with open(full_path) as f:
        text = f.read()

    assert text == content