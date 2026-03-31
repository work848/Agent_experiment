import json

import pytest
from pprint import pprint
from agent.nodes import planner_node as planner_module
from agent.nodes.planner_node import planner_node
from agent.state import AgentState, NextNode, Requirement


def test_planner_node_no_requirements():
    state = AgentState(
        session_id="test-session",
        trigger_plan=True,
        messages=[{"role": "user", "content": "请帮我规划"}],
    )

    result = planner_node(state)

    assert result["trigger_plan"] is False
    assert result["interface_refresh"] is False
    assert result["current_agent"] == "planner"
    assert result["messages"][-1]["role"] == "assistant"
    assert "当前没有可规划的需求" in result["messages"][-1]["content"]


def test_planner_node_with_requirement(monkeypatch):
    requirement = Requirement(
        id="R001",
        title="用户登录",
        description="作为注册用户，我需要通过邮箱和密码登录系统。",
        acceptance_criteria=[
            "提供邮箱输入框",
            "提供密码输入框",
            "登录成功后跳转到首页",
        ],
        priority=1,
    )
    state = AgentState(
        session_id="test-session",
        trigger_plan=True,
        requirements=[requirement],
    )

    captured_messages = {}

    def fake_call_gpt(*, messages, **kwargs):
        captured_messages["messages"] = messages
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "plan": [
                                    {
                                        "id": "R001-S01",
                                        "description": "搭建登录页面 UI",
                                    },
                                    {
                                        "id": "R001-S02",
                                        "description": "实现登录接口并接入页面",
                                    },
                                ]
                            }
                        )
                    }
                }
            ]
        }

    monkeypatch.setattr(planner_module, "call_gpt", fake_call_gpt)

    result = planner_node(state)
    pprint(f"{result}")
    assert result["trigger_plan"] is False
    assert result["interface_refresh"] is True
    assert [step.id for step in result["plan"]] == ["R001-S01", "R001-S02"]
    assert result["requirements"][0].step_ids == ["R001-S01", "R001-S02"]

    llm_messages = captured_messages["messages"]
    assert llm_messages[0]["role"] == "system"
    assert "用户登录" in llm_messages[1]["content"]
    assert "提供邮箱输入框" in llm_messages[1]["content"]
    assert result["retry_count"] == 0
    assert result["retrying_node"] is None
    assert result["last_error_message"] is None


def test_planner_node_routes_to_error_on_invalid_json(monkeypatch):
    requirement = Requirement(
        id="R001",
        title="用户登录",
        description="作为注册用户，我需要通过邮箱和密码登录系统。",
    )
    state = AgentState(
        session_id="test-session",
        trigger_plan=True,
        requirements=[requirement],
    )

    def fake_call_gpt(*, messages, **kwargs):
        return {
            "choices": [
                {
                    "message": {
                        "content": "not-json"
                    }
                }
            ]
        }

    monkeypatch.setattr(planner_module, "call_gpt", fake_call_gpt)

    result = planner_node(state)

    assert result["current_agent"] == NextNode.PLANNER
    assert result["last_failed_node"] == NextNode.PLANNER
    assert result["next_node"] == NextNode.ERROR
    assert result["last_error_message"] == "规划节点（planner）生成失败。"
    assert result["progress_text"] == "当前进度：需求已整理，等待重新生成开发计划。"
