import os
import subprocess
import sys

from tools.base_tool import tool
from config.workspace_config import WORKSPACE, BLOCKED_KEYWORDS


@tool
def run_python(path: str, timeout: str = "5", max_output: str = "2000") -> str:
    """
    Execute a Python file inside the project sandbox.

    Args:
        path: python file path relative to project root
        timeout: max execution time (seconds)
        max_output: max characters returned
    """

    try:
        timeout = int(timeout)
        max_output = int(max_output)
    except:
        return "Error: timeout and max_output must be integers."

    target_path = os.path.abspath(os.path.join(WORKSPACE, path))

    # -------- 安全检查1：路径必须在项目内 --------
    if not target_path.startswith(WORKSPACE):
        return "Error: Access denied."

    # -------- 安全检查2：必须是 python 文件 --------
    if not target_path.endswith(".py"):
        return "Error: Only Python files can be executed."

    # -------- 安全检查3：文件存在 --------
    if not os.path.exists(target_path):
        return "Error: File not found."

    # -------- 安全检查4：禁止危险代码 --------
    try:
        with open(target_path, "r", encoding="utf-8") as f:
            code = f.read()

        for keyword in BLOCKED_KEYWORDS:
            if keyword in code:
                return f"Error: Dangerous keyword detected: {keyword}"

    except:
        return "Error: Cannot read file."

    # -------- 执行代码 --------
    try:
        result = subprocess.run(
            [sys.executable, target_path],
            cwd=WORKSPACE,
            capture_output=True,
            text=True,
            timeout=timeout
        )

        output = result.stdout + result.stderr

        if len(output) > max_output:
            output = output[:max_output] + "\n...output truncated..."

        return (
            f"EXECUTED: {path}\n"
            f"RETURN CODE: {result.returncode}\n\n"
            f"{output}"
        )

    except subprocess.TimeoutExpired:
        return "Error: Execution timed out."

    except Exception as e:
        return f"Execution error: {str(e)}"