from langgraph.graph import StateGraph, END

from agent.state import AgentState

from agent.nodes.planner_node import planner_node
from agent.nodes.interface_build_node import interface_node
from agent.nodes.coder_node import coder_node
from agent.nodes.executor_node import executor_node
from agent.nodes.tester_node import tester_node
from agent.nodes.tool_node import tool_node
from agent.nodes.coordinator_node import central_coordinator

def build_hub_graph():
    graph = StateGraph(AgentState)

    # 注册所有执行节点
    graph.add_node("planner", planner_node)
    graph.add_node("interface", interface_node)
    # graph.add_node("coder", coder_node)
    # graph.add_node("executor", executor_node)
    # graph.add_node("tester", tester_node)

    # 入口直接交给调度员（在这里我们用一个虚拟起点，或者让 planner 作为起点）
    graph.set_entry_point("planner") 

    # --- 核心改动：所有节点执行完都必须“回到”调度决策点 ---
    # 在 LangGraph 中，我们通过给每个节点添加去往“调度判断”的条件边来实现
    
    nodes = ["planner", "interface"]
    for node in nodes:
        graph.add_conditional_edges(
            node,
            central_coordinator, # 每一站结束都问调度员：下一步去哪？
            {
                "planner": "planner",
                "interface": "interface",
                # "coder": "coder",
                # "executor": "executor",
                # "tester": "tester",
                END: END
            }
        )

    return graph.compile()