import sys
import os
# 把 src 目录加入到搜索路径中
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.graph.build_graph import build_graph

graph = build_graph()

state = {
    "messages": [
        {"role": "user", "content": "latest news about Nvidia"}
    ]
}

result = graph.invoke(state)

print(result)