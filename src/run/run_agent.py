# agent_runner.py
from agent.graph.build_graph import build_graph

graph = build_graph()
state = {"messages": []}  # 初始空对话

# 用户输入
user_input = "Hello, can you introduce yourself?"
state["messages"].append({"role": "user", "content": user_input})

# 调用 Agent
state = graph.run(state)

print("Assistant:", state["messages"][-1]["content"])