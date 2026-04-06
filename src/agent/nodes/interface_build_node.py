import json
import uuid
from datetime import datetime, timezone
from typing import List, Dict
from llm.openai_client import call_gpt
from agent.state import (
    InterfaceDesignOutput,
    AgentState,
    ApprovalRequest,
    ApprovalStatus,
    ApprovalType,
    NextNode,
    PlanStatus,
    RunStatus,
    StepStatus,
)
from code_indexer.get_workspace_skeleton import get_workspace_skeleton_direct
from utils.extract_json import extract_json

SCHEMA = json.dumps(
    InterfaceDesignOutput.model_json_schema(),
    indent=2
)

SYSTEM_PROMPT = f"""
You are a software architect.

Design function interfaces for the development steps.

Return ONLY valid JSON.

The output MUST follow this JSON schema:

{SCHEMA}

IMPORTANT RULES:
- DO NOT call any tools
- DO NOT access files
- DO NOT attempt to read uploads
- Only return structured interface definitions
- A step may require multiple functions or classes. Put the primary interface in `interface` and any additional ones in `extra_interfaces`.

Return JSON only.
"""
def _make_execute_plan_approval(existing: list[ApprovalRequest]) -> list[ApprovalRequest]:
    """Return updated approvals with exactly one pending EXECUTE_PLAN per session.

    - 如果已经有 pending 的 EXECUTE_PLAN，就更新那一条（刷新时间、理由等），不再追加新的。
    - 如果没有 pending 的 EXECUTE_PLAN，就在末尾追加一条新的。
    - 非 pending 的审批原样保留，作为历史记录。
    """
    updated: list[ApprovalRequest] = []
    pending_updated = False

    for approval in existing:
        if approval.type == ApprovalType.EXECUTE_PLAN and approval.status == ApprovalStatus.PENDING:
            # 更新现有的 pending execute_plan 审批，而不是再追加一条
            new_item = approval.model_copy(
                update={
                    "title": "Execute plan",
                    "description": "Plan is ready. Approve to start execution.",
                    "reason": "Plan and interface definitions are complete.",
                    "blocking": True,
                }
            )
            updated.append(new_item)
            pending_updated = True
        else:
            updated.append(approval)

    if pending_updated:
        return updated

    # 没有 pending 的 EXECUTE_PLAN，就创建一条新的
    approval = ApprovalRequest(
        id=str(uuid.uuid4()),
        type=ApprovalType.EXECUTE_PLAN,
        title="Execute plan",
        description="Plan is ready. Approve to start execution.",
        created_at=datetime.now(timezone.utc).isoformat(),
        blocking=True,
        status=ApprovalStatus.PENDING,
        requested_action="execute_plan",
        reason="Plan and interface definitions are complete.",
    )
    updated.append(approval)
    return updated


def interface_node(state: AgentState):
    """
    1. 将输入的 Dict 转换为 AgentState 对象
    2. 使用点符号 (.) 访问属性和 Pydantic V2 的 model_copy 方法
    3. 返回时将对象转回 Dict
    """
    print("PLAN STEPS:")
    steps_to_design = [
        s for s in state.plan
        if s.interface is None and s.status == StepStatus.PENDING
    ]

    if not steps_to_design:
        updated_approvals = _make_execute_plan_approval(state.pending_approvals)
        return {
            "interface_refresh": False,
            "current_agent": NextNode.INTERFACE,
            "trigger_plan": False,
            "retrying_node": None,
            "plan_status": PlanStatus.READY,
            "run_status": RunStatus.WAITING_APPROVAL,
            "approval_required": True,
            "approval_type": ApprovalType.EXECUTE_PLAN,
            "approval_payload": None,
            "pending_approvals": updated_approvals,
        }

    skeleton_context = get_workspace_skeleton_direct(state.workspace_root)
    llm_messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Workspace structure:\n{skeleton_context}\n\nSteps:\n{steps_to_design}\n\nDesign interfaces."
        }
    ]

    try:
        response = call_gpt(messages=llm_messages, tools=None)
        content = response["choices"][0]["message"]["content"]
        json_text = extract_json(content)
        design_data = InterfaceDesignOutput.model_validate_json(json_text)
    except Exception:
        return {
            "trigger_plan": False,
            "interface_refresh": False,
            "current_agent": NextNode.INTERFACE,
            "last_failed_node": NextNode.INTERFACE,
            "last_error_message": "接口节点（interface）生成失败。",
            "next_node": NextNode.ERROR,
            "retrying_node": None,
            "progress_text": "当前进度：开发计划已生成，等待重新补全接口定义。",
            "run_status": RunStatus.BLOCKED,
            "approval_required": False,
            "approval_type": None,
            "approval_payload": None,
        }

    design_map = {item.step_id: item for item in design_data.interfaces}
    new_plan = []

    for step in state.plan:
        if step.id in design_map:
            task = design_map[step.id]
            new_step = step.model_copy(
                update={
                    "interface": task.interface,
                    "extra_interfaces": task.extra_interfaces,
                }
            )
        else:
            new_step = step
        new_plan.append(new_step)

    updated_approvals = _make_execute_plan_approval(state.pending_approvals)
    return {
        "plan": new_plan,
        "current_agent": NextNode.INTERFACE,
        "interface_refresh": False,
        "trigger_plan": False,
        "last_failed_node": None,
        "last_error_message": None,
        "retry_count": 0,
        "retrying_node": None,
        "progress_text": "当前进度：接口定义已补全，等待确认执行。",
        "next_node": None,
        "plan_status": PlanStatus.READY,
        "run_status": RunStatus.WAITING_APPROVAL,
        "approval_required": True,
        "approval_type": ApprovalType.EXECUTE_PLAN,
        "approval_payload": None,
        "pending_approvals": updated_approvals,
    }
