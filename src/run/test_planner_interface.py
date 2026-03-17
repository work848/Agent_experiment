# src/run/test_simple_planner_interface.py

from agent.state import AgentState, Step, StepStatus
from agent.nodes.interface_build_node import interface_node
from agent.nodes.planner_node import planner_node
from pprint import pprint

# ---------------------------
# Build initial test state
# ---------------------------
def build_test_state():

    state = AgentState(
        session_id="test-session",
        messages=[{"role": "user", "content": "Build a simple calculator"}],
        workspace_root=".",
        plan=[],
        current_step=0,
    )
    return state


# ---------------------------
# Simple linear test
# ---------------------------
def main():
    state = build_test_state()

    print("\n===== RUNNING planner_node =====")
    planner_node(state)
    for step in state.plan:
        print(f"Step {step.id}: interface={step.interface}, status={step.status}")

    print("\n===== RUNNING interface_node =====")
    pprint(state)
    output = interface_node(state)  # 直接传 state 对象
    new_plan = output.get("plan", [])

    print("\n===== AFTER interface_node =====")
    for step in new_plan:
        # step 可能是对象，也可能是 dict，用 pprint 安全打印
        pprint(step)


if __name__ == "__main__":
    main()