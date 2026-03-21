from dotenv import load_dotenv
import json 
load_dotenv("APIKey.env")
from agent.nodes.interface_build_node import interface_node
from agent.state import AgentState, Step, StepStatus
from pprint import pprint
load_dotenv("APIKey.env")
def build_test_state():

    plan = [
        Step(
            id="R001-S01",
            description="Create main calculator module with add function",
            interface=None,
            implementation_file="calculator.py",
            status=StepStatus.PENDING,
            retries=0
        ),
        Step(
            id="R001-S02",
            description="Implement subtract function in calculator module",
            interface=None,
            implementation_file="calculator.py",
            status=StepStatus.PENDING,
            retries=0
        ),
        Step(
            id="R001-S03",
            description="Create main entry point with user interface for calculator operations",
            interface=None,
            implementation_file="main.py",
            status=StepStatus.PENDING,
            retries=0
        ),
        Step(
            id="R001-S04",
            description="Write unit tests for add and subtract functions",
            interface=None,
            implementation_file="test_calculator.py",
            status=StepStatus.PENDING,
            retries=0
        ),
    ]

    state = AgentState(
        session_id="test-session",
        messages=[
            {
                "role": "user",
                "content": "Build a simple calculator project"
            }
        ],
        workspace_root=".",
        plan=plan,
        current_step=0
    )

    return state


def main():
    state = build_test_state()

    print("\n===== BEFORE =====\n")
    # 直接对象访问，很爽
    for step in state.plan:
        print(f"ID: {step.id}, Status: {step.status}")

    print("\n===== RUNNING interface_node =====\n")

    # 【关键修改】直接传对象
    output = interface_node(state) 

    print("\n===== OUTPUT =====\n")

    # 此时 output 通常是一个 dict（因为节点返回的是增量更新）
    new_plan_dicts = output.get("plan", [])

    for step_dict in new_plan_dicts:
        # 打印时，因为是 dict，用 json.dumps 没问题
        print(json.dumps(step_dict, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()