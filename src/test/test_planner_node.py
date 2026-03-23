import os
from dotenv import load_dotenv

load_dotenv("APIKey.env")

from agent.nodes.planner_node import planner_node


def test_planner_node_simple():

    state = {
        "messages": [
            {
                "role": "user",
                "content": "build a python calculator with add and sub functions"
            }
        ],
        "requirements":[],
        "plan": [],
        "workspace_root": "./",
        "current_step": 0
    }

    print("\n===== Running planner_node =====\n")

    output = planner_node(state)

    print("\n===== Planner Output =====\n")
    print(output)

    print("\n===== Generated Plan =====\n")

    for step in output["plan"]:
        print(
            f"ID: {step.id} | "
            f"Status: {step.status} | "
            f"Description: {step.description}"
        )

    print("\n===== Test Finished =====\n")