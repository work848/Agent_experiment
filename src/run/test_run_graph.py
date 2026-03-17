from pprint import pprint

from agent.graph import build_graph
from agent.state import AgentState
from agent.graph.build_graph import build_hub_graph


def build_test_state():

    state = AgentState(
        session_id="test-session",
        messages=[{"role": "user", "content": "Build a simple calculator"}],
        workspace_root=".",
        plan=[],
        current_step=0,
    )

    return state


def main():

    # 1️⃣ 初始化 state
    state = build_test_state()

    # 2️⃣ 构建 LangGraph
    graph = build_hub_graph()

    print("\n===== RUNNING GRAPH =====")

    # 3️⃣ 执行 graph
    result = graph.invoke(state)

    print("\n===== FINAL STATE =====")

    print("\n===== PLAN =====")
    if result["plan"]:
        for step in result["plan"]:
            pprint(step)
    else:
        print("No plan generated")


if __name__ == "__main__":
    main()