import os
from dotenv import load_dotenv

# 只加载一次
load_dotenv("workspace.env")

WORKSPACE = os.getenv("WORKSPACE")

if not WORKSPACE:
    raise ValueError("WORKSPACE not defined in workspace.env")

WORKSPACE = os.path.abspath(WORKSPACE)

BLOCKED_FILES = {
    "workspace.env",
    ".git",
    "core",
    "system"
}
BLOCKED_KEYWORDS = [
    "os.system",
    "subprocess",
    "eval(",
    "exec(",
    "__import__",
    "open(",
]

ALLOWED_WRITE_DIRS = {
    "tools",
    "workspace"
}
ALLOWED_EXT = {
    ".py",
    ".txt",
    ".json",
    ".md",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".html",
    ".css",
}
# Agent 忽略的目录
IGNORE_DIRS = {
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build"
}

# 忽略文件类型
IGNORE_EXT = {
    ".log",
    ".lock",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".mp4",
    ".zip"
}

SKIP_FUNCTIONS = {
    'print', 'len', 'append', 'str', 'int', 'dict', 'list', 
    'json.dumps', 'json.loads', 'endswith', 'startswith', 
    'isinstance', 'type', 'range', 'enumerate'
}

MAX_FILE_SIZE = 200000
MAX_PATCH_LINES = 200
MAX_PATH_DEPTH = 5