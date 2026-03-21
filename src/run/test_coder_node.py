from dotenv import load_dotenv
load_dotenv("APIKey.env")

import json
import logging
from agent.nodes.coder_node import coder_node
from agent.state import AgentState, Step, StepStatus, Interface, Parameter

# 打开日志，方便看 coder_node 内部的执行过程
logging.basicConfig(level=logging.INFO, format="%(name)s | %(levelname)s | %(message)s")


def build_test_state():
    """
    第二轮测试：add/subtract/main 已经实现（SUCCESS），
    新增 multiply 和 divide，看 coder 能否在已有文件上扩展。
    """
    plan = [
        # ===== 已实现的步骤（模拟上一轮的成果）=====
        Step(
            id="R001-S01",
            description="Implement add function",
            interface=Interface(
                name="add",
                parameters=[
                    Parameter(name="a", type="float"),
                    Parameter(name="b", type="float"),
                ],
                return_type="float",
                description="Return the sum of a and b",
                dependencies=[],
            ),
            implementation_file="calculator/math_ops.py",
            status=StepStatus.SUCCESS,  # ← 已完成
        ),
        Step(
            id="R001-S02",
            description="Implement subtract function",
            interface=Interface(
                name="subtract",
                parameters=[
                    Parameter(name="a", type="float"),
                    Parameter(name="b", type="float"),
                ],
                return_type="float",
                description="Return a minus b",
                dependencies=[],
            ),
            implementation_file="calculator/math_ops.py",
            status=StepStatus.SUCCESS,  # ← 已完成
        ),
        Step(
            id="R001-S03",
            description="Implement calculator main entry point",
            interface=Interface(
                name="main",
                parameters=[],
                return_type="None",
                description="CLI calculator with add and subtract",
                dependencies=["R001-S01", "R001-S02"],
            ),
            implementation_file="calculator/main.py",
            status=StepStatus.SUCCESS,  # ← 已完成
        ),

        # ===== 新增的步骤，需要在已有代码上扩展 =====
        Step(
            id="R002-S01",
            description="Add multiply function to existing math_ops module",
            interface=Interface(
                name="multiply",
                parameters=[
                    Parameter(name="a", type="float"),
                    Parameter(name="b", type="float"),
                ],
                return_type="float",
                description="Return a multiplied by b. Add this function to the existing math_ops.py file that already has add and subtract.",
                dependencies=["R001-S01", "R001-S02"],  # 依赖已有的 math_ops
            ),
            implementation_file="calculator/math_ops.py",
            status=StepStatus.PENDING,
        ),
        Step(
            id="R002-S02",
            description="Add divide function to existing math_ops module",
            interface=Interface(
                name="divide",
                parameters=[
                    Parameter(name="a", type="float"),
                    Parameter(name="b", type="float"),
                ],
                return_type="float",
                description="Return a divided by b. Handle division by zero. Add this function to the existing math_ops.py file that already has add, subtract, and multiply.",
                dependencies=["R001-S01", "R001-S02", "R002-S01"],  # 依赖已有的 + multiply
            ),
            implementation_file="calculator/math_ops.py",
            status=StepStatus.PENDING,
        ),
    ]

    state = AgentState(
        session_id="test-coder-round2",
        messages=[
            {"role": "user", "content": "Extend the calculator with multiply and divide functions"}
        ],
        workspace_root=r"C:\temp",
        plan=plan,
        current_step=0,
    )
    return state


def main():
    state = build_test_state()

    print("\n===== BEFORE CODER =====\n")
    for step in state.plan:
        print(f"  Step {step.id}: [{step.status.value}] {step.description}")

    print("\n===== RUNNING coder_node =====\n")
    output = coder_node(state)

    print("\n===== AFTER CODER =====\n")
    new_plan = output.get("plan", [])
    for step in new_plan:
        status = step.status.value if hasattr(step.status, "value") else step.status
        print(f"  Step {step.id}: [{status}] {step.description}")
        if step.implementation_file:
            print(f"           -> file: {step.implementation_file}")


if __name__ == "__main__":
    main()
