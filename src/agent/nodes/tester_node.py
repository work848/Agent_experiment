from llm.openai_client import call_gpt
import logging

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
You are a software tester.

Analyze the execution result.

If the code succeeded, respond with SUCCESS.

If there is an error, explain the problem.
"""

def tester_node(state):

    result = state["execution_result"]

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": result}
    ]

    response = call_gpt(messages=messages)

    content = response["choices"][0]["message"]["content"]

    success = "SUCCESS" in content.upper()

    new_state = dict(state)

    new_state["success"] = success

    new_state["messages"] = state["messages"] + [
        {"role": "assistant", "content": content}
    ]

    if not success:
        new_state["current_step"] += 1

    return new_state