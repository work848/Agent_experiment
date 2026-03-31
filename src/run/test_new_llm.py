import os
from dotenv import load_dotenv
import requests
import json
import logging
from langchain_core.utils.function_calling import convert_to_openai_tool
from agent.state import AgentState 
from pprint import pprint
load_dotenv()

API_URL = "https://api.deepseek.com/v1/chat/completions"
API_KEY = "sk-9ae89b956b1341aa9d0a3b194f3b2581"


def call_gpt(messages, model="deepseek-coder",response_format: str = None, tools: list = None, temperature: float = 0.6, max_tokens: int = 4096):

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    body = {
        "model": model,
        "messages": messages,
        "temperature": temperature, # 默认加上低温，防止发散
        "max_tokens": max_tokens    # 确保代码生成的上下文长度足够
    }


    resp = requests.post(API_URL, json=body, headers=headers)

    resp.raise_for_status()
    try:
        data = resp.json()
        return data
    except Exception as e:
        print("虽然返回了 200，但内容不是标准的 JSON 格式！")
        return resp.text

state1 = [{
    "role": "user", "content":"hello"   
}]

result = call_gpt(state1)
print(result)