from pprint import pprint

import pytest
from agent.nodes.chat_node import chat_node
from agent.state import AgentState


def test_chat_node_triggers_planning_with_fallback():
    state = AgentState(
        session_id="session-1",
        trigger_plan=False,
        messages=[
            {"role": "user", "content": "hello"  }],
        
        requirements=[],
    )

    result = chat_node(state)
    pprint(result)
    assert result["ready_for_plan"] is True
    assert result["trigger_plan"] is True
    assert result["next_node"].value == "planner"
    assert len(result["requirements"]) == 0


# def test_chat_node_chat_response():
#     state = AgentState(
#         session_id="session-2",
#         trigger_plan=False,
#         messages=[
#             {"role": "user", "content": "你好"},
#         ],
#     )


#     result = chat_node(state)

#     assert result["ready_for_plan"] is False
#     assert result["messages"][-1]["content"] == "请提供更多需求细节"
#     assert result["suggested_actions"] == []
if __name__ == "__main__":
    # 手动调用这个测试函数
    test_chat_node_triggers_planning_with_fallback()