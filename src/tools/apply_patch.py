import os

from tools.base_tool import tool
from config.workspace_config import BLOCKED_KEYWORDS, WORKSPACE, BLOCKED_FILES


@tool
def apply_patch(
    path: str,
    start_line: str,
    end_line: str,
    new_code: str
) -> str:
    """
    Replace lines in a file with new code.

    Args:
        path: file path relative to project root
        start_line: starting line number (1-indexed)
        end_line: ending line number (1-indexed)
        new_code: code to replace
    """

    try:
        start_line = int(start_line)
        end_line = int(end_line)
    except:
        return "Error: start_line and end_line must be integers."

    target_path = os.path.abspath(os.path.join(WORKSPACE, path))

    # -------- 安全检查1：路径限制 --------
    if not target_path.startswith(WORKSPACE):
        return "Error: Access denied."

    # -------- 安全检查2：禁止修改 protected 文件 --------
    if os.path.basename(target_path) in BLOCKED_FILES:
        return "Error: This file cannot be modified."

    # -------- 文件存在 --------
    if not os.path.exists(target_path):
        return "Error: File not found."
    # -------- 安全检查3：禁止访问 .git --------
    if ".git" in target_path:
        return "Error: .git access denied"
    # -------- 安全检查4：禁止危险关键词 --------
    for keyword in BLOCKED_KEYWORDS:
        if keyword in new_code:
            return f"Error: dangerous keyword detected: {keyword}"
    
    try:
        with open(target_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        total_lines = len(lines)

        if start_line < 1 or end_line > total_lines or start_line > end_line:
            return f"Error: Invalid line range. File has {total_lines} lines."

        # Python index
        start_idx = start_line - 1
        end_idx = end_line

        new_lines = new_code.splitlines(keepends=True)

        updated_lines = lines[:start_idx] + new_lines + lines[end_idx:]

        with open(target_path, "w", encoding="utf-8") as f:
            f.writelines(updated_lines)

        return (
            f"PATCH APPLIED\n"
            f"FILE: {path}\n"
            f"REPLACED LINES: {start_line}-{end_line}\n"
            f"NEW LINES: {len(new_lines)}"
        )

    except Exception as e:
        return f"Patch error: {str(e)}"