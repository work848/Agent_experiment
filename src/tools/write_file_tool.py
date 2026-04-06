import os
from dotenv import load_dotenv
from tools.base_tool import tool
# 加载 workspace.env
from config.workspace_config import ALLOWED_EXT, BLOCKED_KEYWORDS, MAX_FILE_SIZE, WORKSPACE, BLOCKED_FILES

if not WORKSPACE:
    raise ValueError("WORKSPACE not defined in workspace.env")

@tool
def write_file(path: str, content: str) -> str:
    """
    Write content to a file inside the Agent_project directory.

    Security rules:
    - Must stay inside Agent_project
    - Cannot modify workspace.env
    """

    project_root = os.path.abspath(WORKSPACE)

    # 目标路径
    target_path = os.path.abspath(os.path.join(project_root, path))

    # -------- 安全检查1：必须在项目目录内 --------
    if not target_path.startswith(project_root):
        return "Error: Access denied. Path must stay inside Agent_project."

    # -------- 安全检查2：禁止修改 blocked files --------
    if os.path.basename(target_path) in BLOCKED_FILES:
        return "Error: This file cannot be modified."
    # -------- 安全检查3：禁止访问 .git --------
    if ".git" in target_path:
        return "Error: .git access denied"
    # -------- 安全检查4：禁止危险关键词（仅针对 Python 文件） --------
    ext = os.path.splitext(target_path)[1]
    if ext not in ALLOWED_EXT:
        return "Error: file type not allowed"

    if ext == ".py":
        for keyword in BLOCKED_KEYWORDS:
            if keyword in content:
                return f"Error: dangerous keyword detected: {keyword}"
    
    
    # 创建目录
    os.makedirs(os.path.dirname(target_path), exist_ok=True)

    # 写入文件
    with open(target_path, "w", encoding="utf-8") as f:
        if len(content) > MAX_FILE_SIZE:
            return "Error: file too large"
        f.write(content)

    return f"File written successfully: {path}"