import os
from tools.base_tool import tool
from config.workspace_config import WORKSPACE, IGNORE_DIRS


@tool
def read_file(path: str, start_line: str = "0", max_lines: str = "200") -> str:
    """
    Read a file from the project.

    Args:
        path: file path relative to project root
        start_line: line number to start reading
        max_lines: maximum lines to read
    """

    try:
        start_line = int(start_line)
        max_lines = int(max_lines)
    except:
        return "Error: start_line and max_lines must be integers."

    target_path = os.path.abspath(os.path.join(WORKSPACE, path))

    # -------- 安全检查1：路径必须在项目内 --------
    if not target_path.startswith(WORKSPACE):
        return "Error: Access denied."

    # -------- 安全检查2：文件必须存在 --------
    if not os.path.exists(target_path):
        return "Error: File not found."

    # -------- 忽略目录 --------
    for ignore_dir in IGNORE_DIRS:
        if f"{os.sep}{ignore_dir}{os.sep}" in target_path:
            return "Error: Access to ignored directory."

    try:
        with open(target_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        total_lines = len(lines)

        end_line = min(start_line + max_lines, total_lines)

        selected_lines = lines[start_line:end_line]

        content = "".join(selected_lines)

        return (
            f"FILE: {path}\n"
            f"LINES: {start_line}-{end_line} / {total_lines}\n\n"
            f"{content}"
        )

    except Exception as e:
        return f"Error reading file: {str(e)}"