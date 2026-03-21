from dotenv import load_dotenv
load_dotenv("APIKey.env")

import json
import logging
from agent.nodes.coder_node import coder_node
from agent.state import AgentState, Step, StepStatus, Interface, Parameter

# 打开日志
logging.basicConfig(level=logging.INFO, format="%(name)s | %(levelname)s | %(message)s")


def build_advanced_test_state():
    """
    Advanced Test:
    1. Create a NEW file (`advanced_ops.py`) for a function.
    2. EDIT that file to add another function (`factorial`).
    3. Create a NEW class file (`calculator_class.py`) that has DEPENDENCIES on `math_ops.py` and `advanced_ops.py`.
    """
    plan = [
        # ===== PRE-EXISTING (math_ops.py already exists from previous tests) =====
        Step(
            id="R001-S01",
            description="Implement basic math operations",
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
            status=StepStatus.SUCCESS,
        ),

        # ===== AUGMENTED PENDING STEPS =====
        Step(
            id="R002-S01",
            description="Create advanced operations module with power function",
            interface=Interface(
                name="power",
                parameters=[
                    Parameter(name="base", type="float"),
                    Parameter(name="exponent", type="float"),
                ],
                return_type="float",
                description="Return base raised to the power of exponent.",
                dependencies=[],
            ),
            implementation_file="calculator/advanced_ops.py",
            status=StepStatus.PENDING,  # Should generate a NEW file
        ),
        Step(
            id="R002-S02",
            description="Add factorial function to advanced operations",
            interface=Interface(
                name="factorial",
                parameters=[
                    Parameter(name="n", type="int"),
                ],
                return_type="int",
                description="Return the factorial of n. Must be added to the existing advanced_ops.py module.",
                dependencies=["R002-S01"],
            ),
            implementation_file="calculator/advanced_ops.py",
            status=StepStatus.PENDING,
        ),
        Step(
            id="R003-S01",
            description="Create a Calculator class combining basic and advanced ops",
            interface=Interface(
                name="Calculator",
                parameters=[],
                return_type="None",
                description="Create a class `Calculator` that exposes `add_numbers`, `power_numbers`, and `factorial_number` methods by delegating to the functions in math_ops and advanced_ops.",
                dependencies=["R001-S01", "R002-S01", "R002-S02"],
            ),
            implementation_file="calculator/calculator_class.py",
            status=StepStatus.PENDING,
        ),
    ]

    state = AgentState(
        session_id="test-coder-advanced",
        messages=[
            {"role": "user", "content": "Build advanced components and integrate them into a class layer."}
        ],
        workspace_root=r"C:\temp\testFolder",
        plan=plan,
        current_step=0,
    )
    return state


def main():
    state = build_advanced_test_state()

    print("\n===== BEFORE CODER (ADVANCED TEST) =====\n")
    for step in state.plan:
        print(f"  Step {step.id}: [{step.status.value}] {step.description}")

    print("\n===== RUNNING coder_node =====\n")
    output = coder_node(state)

    print("\n===== AFTER CODER (ADVANCED TEST) =====\n")
    new_plan = output.get("plan", [])
    for step in new_plan:
        status = step.status.value if hasattr(step.status, "value") else step.status
        print(f"  Step {step.id}: [{status}] {step.description}")
        if step.implementation_file:
            print(f"           -> file: {step.implementation_file}")


if __name__ == "__main__":
    main()
