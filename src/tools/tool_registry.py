# 导入所有 tool 文件（触发注册）
from tools.load_tools import load_all_tools
from tools.base_tool import REGISTERED_TOOLS
load_all_tools()




TOOLS = [schema for schema, _ in REGISTERED_TOOLS]

TOOL_MAP = {
    schema["function"]["name"]: func
    for schema, func in REGISTERED_TOOLS
}