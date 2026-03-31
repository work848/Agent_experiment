"""Mechanical enforcement of node return-dict contracts.

Call `assert_execution_node_contract(result, node_name)` in tests or node
wrappers to verify that an execution node's return dict contains all required
fields before the result is merged into AgentState.
"""

from typing import Any, Dict

# Fields that every execution node (coder, tester) must include in its return dict.
# Planning nodes (planner, interface, chat, error) are excluded — they operate on
# a different state surface and do not own run/evidence fields.
EXECUTION_NODE_REQUIRED_FIELDS = [
    "run_status",
    "last_outcome",
    "last_evidence",
    "current_agent",
    "next_node",
]


class NodeContractViolation(Exception):
    """Raised when a node return dict is missing required contract fields."""


def assert_execution_node_contract(result: Dict[str, Any], node_name: str) -> None:
    """Raise NodeContractViolation if result is missing any required field.

    Args:
        result: The dict returned by a node function.
        node_name: Name of the node (used in error messages).
    """
    missing = [f for f in EXECUTION_NODE_REQUIRED_FIELDS if f not in result]
    if missing:
        raise NodeContractViolation(
            f"Node '{node_name}' return dict is missing required fields: {missing}"
        )
