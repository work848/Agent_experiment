from langgraph.graph import StateGraph, START, END

from agent.nodes.chat_node import chat_node
from agent.state import AgentState

from agent.nodes.planner_node import planner_node
from agent.nodes.interface_build_node import interface_node
from agent.nodes.coder_node import coder_node
from agent.nodes.executor_node import executor_node
from agent.nodes.tester_node import tester_node
from agent.nodes.tool_node import tool_node
from agent.nodes.coordinator_node import central_coordinator
from agent.nodes.error_node import error_node


def build_hub_graph():
    graph = StateGraph(AgentState)

    # 注册所有执行节点
    graph.add_node("chat", chat_node)
    graph.add_node("planner", planner_node)
    graph.add_node("interface", interface_node)
    graph.add_node("error", error_node)
    graph.add_node("coder", coder_node)
    graph.add_node("tester", tester_node)

    # 入口直接交给调度员，由当前状态决定首个真正执行的节点
    graph.add_conditional_edges(
        START,
        central_coordinator,
        {
            "planner": "planner",
            "interface": "interface",
            "chat": "chat",
            "coder": "coder",
            "tester": "tester",
            "error": "error",
            END: END,
        },
    )

    # --- 核心改动：所有节点执行完都必须“回到”调度决策点 ---
    # 在 LangGraph 中，我们通过给每个节点添加去往“调度判断”的条件边来实现
    nodes = ["chat", "planner", "interface", "error", "coder", "tester"]
    for node in nodes:
        graph.add_conditional_edges(
            node,
            central_coordinator,  # 每一站结束都问调度员：下一步去哪？
            {
                "planner": "planner",
                "interface": "interface",
                "chat": "chat",
                "coder": "coder",
                "tester": "tester",
                "error": "error",
                END: END,
            },
        )

    return graph.compile()


def build_graph():
    return build_hub_graph()
