import os
from dotenv import load_dotenv
import requests
import json
import logging
from agent.state import AgentState
from tools.tool_registry import TOOLS
from langchain_core.utils.function_calling import convert_to_openai_tool
from agent.state import AgentState 
 

API_URL = "https://ai.huan666.de/v1/chat/completions"
API_KEY = os.getenv("NEW_API_LLM_API_KEY")

OPENAI_TOOLS = [convert_to_openai_tool(t) for t in TOOLS]

def call_gpt(messages, model="claude-haiku-4-5-20251001",response_format: str = None, tools: list = None):

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    body = {
        "model": model,
        "messages": messages,
    }
    # 核心逻辑：工具调用和 JSON 模式的平衡
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
        body["temperature"]= 0.3
        # 注意：开启工具时，通常不设置 response_format 为 json_object
    
    if response_format:
        body["response_format"] = response_format
        body["temperature"]= 0.1


    resp = requests.post(API_URL, json=body, headers=headers)

    resp.raise_for_status()

    data = resp.json()
    

    return data



    # body = {
    #     "model": model,
    #     "messages": messages,
    #     "tools": OPENAI_TOOLS,
    #     "tool_choice": "auto",
    #     "temperature": 0.2,
    #     "response_format": {
    #         "type": "json_object"
    #     }
    # }
# {
    #     "role": message.get("role", "assistant"),
    #     "content": message.get("content", ""),
    #     "tool_calls": message.get("tool_calls")
    # }

# 测试
# print(call_gpt([{"role": "user", "content": "Hello"}]))
# {
#   "id": "chatcmpl-123",
#   "object": "chat.completion",
#   "created": 1677652288,
#   "model": "gpt-5.4",
#   "choices": [         // <--- [0] 取这里面的第一个
#     {
#       "index": 0,
#       "message": {     // <--- 你的函数最终返回这个字典
#         "role": "assistant",
#         "content": "你好！有什么我可以帮你的？",
#         "tool_calls": [ ... ] // 如果 AI 决定调用工具，这里会有数据
#       },
#       "finish_reason": "stop"
#     }
#   ],
#   "usage": { ... }
# }