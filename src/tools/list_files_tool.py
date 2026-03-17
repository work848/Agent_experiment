import os
from tools.base_tool import tool
from config.workspace_config import WORKSPACE, IGNORE_DIRS, IGNORE_EXT


@tool
def list_files() -> str:
    """
    List files in the project workspace.
    """

    file_list = []

    for root, dirs, files in os.walk(WORKSPACE):

        # 过滤目录
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]

        for file in files:

            if any(file.endswith(ext) for ext in IGNORE_EXT):
                continue

            full_path = os.path.join(root, file)

            relative_path = os.path.relpath(full_path, WORKSPACE)

            file_list.append(relative_path)

    if not file_list:
        return "Workspace is empty."

    return "\n".join(file_list)