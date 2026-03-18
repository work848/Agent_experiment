from dotenv import load_dotenv
load_dotenv("APIKey.env")

import json
import logging
from agent.nodes.coder_node import coder_node
from agent.state import AgentState, Step, StepStatus, Interface, Parameter

# 打开日志
logging.basicConfig(level=logging.INFO, format="%(name)s | %(levelname)s | %(message)s")


def build_ultimate_test_state():
    """
    Ultimate Stress Test: A realistic Data Processing Pipeline
    Tests: Sub-folder structure nesting, class implementation, list/type hinting, and complex EDIT patching.
    """
    plan = [
        # ----- STEP 1: Base Model (NEW FILE, CLASS) -----
        Step(
            id=1,
            description="Create User data model",
            interface=Interface(
                name="User",
                parameters=[],
                return_type="None",
                description="Using the `dataclasses` module, define a @dataclass called `User` with the following typed fields: `id` (int), `name` (str), `email` (str), and `is_active` (bool).",
                dependencies=[],
            ),
            implementation_file="models/user.py",
            status=StepStatus.SUCCESS,
        ),
        
        # ----- STEP 2: Base Extractor (NEW FILE, FUNCTION) -----
        Step(
            id=2,
            description="Create fetch_users extractor function",
            interface=Interface(
                name="fetch_users",
                parameters=[],
                return_type="list", # Should ideally return List[User], but simplified to 'list' for the LLM
                description="Return a hardcoded list of 3 User objects (from models.user). One should have is_active=False.",
                dependencies=[1],
            ),
            implementation_file="pipeline/extractor.py",
            status=StepStatus.SUCCESS,
        ),
        
        # ----- STEP 3: Base Transformer (NEW FILE, FUNCTION) -----
        Step(
            id=3,
            description="Create filter_active_users transformer function",
            interface=Interface(
                name="filter_active_users",
                parameters=[
                    Parameter(name="users", type="list"),
                ],
                return_type="list",
                description="Given a list of User objects, return a new list containing only the users where is_active is True.",
                dependencies=[1],
            ),
            implementation_file="pipeline/transformer.py",
            status=StepStatus.PENDING,
        ),
        
        # ----- STEP 4: Transformer Patching (EDIT FILE, COMPLEX LOGIC) -----
        # This is where the real stress test happens. It has to PATCH transformer.py
        Step(
            id=4,
            description="Add mask_user_emails to transformer",
            interface=Interface(
                name="mask_user_emails",
                parameters=[
                    Parameter(name="users", type="list"),
                ],
                return_type="list",
                description="Given a list of User objects, iterate through them and mask their emails (e.g., 'john@example.com' becomes 'j***@example.com'). Return the updated list. This MUST be added to the existing transformer module without deleting `filter_active_users`.",
                dependencies=[1, 3],
            ),
            implementation_file="pipeline/transformer.py",
            status=StepStatus.SUCCESS,
        ),
        
        # ----- STEP 5: Main Orchestrator (NEW FILE, CROSS INJECTION) -----
        Step(
            id=5,
            description="Create main pipeline runner",
            interface=Interface(
                name="run_pipeline",
                parameters=[],
                return_type="list",
                description="Import `fetch_users`, `filter_active_users`, and `mask_user_emails`. Call them in sequence: fetch the users, filter the active ones, then mask their emails. Return the final list of masked, active users.",
                dependencies=[2, 3, 4], 
            ),
            implementation_file="main.py",
            status=StepStatus.SUCCESS,
        ),
    ]

    state = AgentState(
        session_id="test-coder-ultimate",
        messages=[
            {"role": "user", "content": "Build a robust Data Processing Pipeline."}
        ],
        workspace_root=r"C:\temp\ultimate_test", # NEW DIRECTORY
        plan=plan,
        current_step=0,
    )
    return state


def main():
    state = build_ultimate_test_state()

    print("\n===== BEFORE CODER (ULTIMATE TEST) =====\n")
    for step in state.plan:
        print(f"  Step {step.id}: [{step.status.value}] {step.description}")

    print("\n===== RUNNING coder_node =====\n")
    output = coder_node(state)

    print("\n===== AFTER CODER (ULTIMATE TEST) =====\n")
    new_plan = output.get("plan", [])
    for step in new_plan:
        status = step.status.value if hasattr(step.status, "value") else step.status
        print(f"  Step {step.id}: [{status}] {step.description}")
        if step.implementation_file:
            print(f"           -> file: {step.implementation_file}")


if __name__ == "__main__":
    main()
