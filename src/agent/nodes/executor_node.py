import logging

from tools.run_python import run_python

logger = logging.getLogger(__name__)

def executor_node(state):

    code = ""

    messages = state["messages"]

    for m in reversed(messages):
        if m["role"] == "assistant":
            code = m["content"]
            break

    result = run_python(code)

    new_state = dict(state)

    new_state["execution_result"] = result

    new_state["messages"] = messages + [
        {"role": "tool", "content": result}
    ]

    return new_state