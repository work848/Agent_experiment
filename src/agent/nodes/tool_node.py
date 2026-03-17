import json
from agent.state import AgentState
from tools.tool_registry import TOOL_MAP
import logging
    
logger = logging.getLogger(__name__)

import json

def tool_node(state: AgentState):

    messages = state.messages

    last_message = messages[-1]

    tool_calls = last_message.get("tool_calls", [])

    if not tool_calls:
        return state

    new_messages = []

    for tool_call in tool_calls:

        tool_name = tool_call["function"]["name"]

        arguments = json.loads(tool_call["function"]["arguments"])

        tool = TOOL_MAP.get(tool_name)

        print("Executing tool:", tool_name)

        try:
            result = tool(**arguments)

            print("TOOL RESULT LENGTH:", len(str(result)))

        except Exception as e:
            result = f"工具执行出错: {str(e)}"

        new_messages.append({
            "role": "tool",
            "tool_call_id": tool_call["id"],
            "content": str(result)
        })

    # 更新 messages
    state.messages = messages + new_messages

    # 工具调用完成
    state.tool_call = None

    return state

    # llm输出格式示例：
#     {
#  "tool_calls": [
#    {
#      "name": "search",
#      "arguments": {
#        "query": "latest AI news"
#      }
#    }
#  ]
# }
