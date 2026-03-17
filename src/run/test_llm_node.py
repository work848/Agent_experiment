import json
import sys
import os
from dotenv import load_dotenv

load_dotenv(dotenv_path="APIKey.env")
# 把 src 目录加入到搜索路径中
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.nodes.llm_node import llm_node


state = {
    "messages": [
        {"role": "user", "content": "Hello, who are you?"}
    ]
}

result = llm_node(state)

print(json.dumps(result, indent=4, ensure_ascii=False))