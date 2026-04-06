import json
import logging
import re
from typing import Dict, List
from pprint import pprint
from llm.openai_client import call_gpt
from agent.state import AgentState, NextNode, PlannerOutput, PlanStatus, RunStatus, ApprovalType, Requirement, Step

logger = logging.getLogger(__name__)


schema = json.dumps(PlannerOutput.model_json_schema(), indent=2)
SYSTEM_PROMPT = f"""
You are a software architect.

Create a development plan from structured requirements.

The plan must be valid JSON matching this schema:
{schema}

Rules:
- Use step IDs linked to requirement IDs in this format: R001-S01, R001-S02.
- Each step should clearly implement part of one requirement.
- dependencies must reference step IDs (string IDs), not requirement IDs.
- Return JSON only.
"""
def get_requirement_from_txt():
    requirements_path = "src/memory/state/Requirement.txt"
    lines: List[str] = []
    with open(requirements_path, "r", encoding="utf-8") as f:
        for line in f:
            clean_line = line.strip()
            if clean_line and not clean_line.startswith("#"):
                lines.append(clean_line)
    return "\n".join(lines)   

def extract_json_from_markdown(text: str) -> str:
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.S)
    if match:
        return match.group(1)

    match = re.search(r"```\s*(\{.*?\})\s*```", text, re.S)
    if match:
        return match.group(1)

    match = re.search(r"\{.*\}", text, re.S)
    if match:
        return match.group()

    raise ValueError("No valid JSON found in response")


def _build_requirements_context(requirements: List[Requirement]) -> str:
    lines: List[str] = []
    for req in requirements:
        lines.append(f"- {req.id} | {req.title}")
        lines.append(f"  Description: {req.description}")
        lines.append(f"  Priority: {req.priority}")
        lines.append(f"  Status: {req.status.value}")
        if req.acceptance_criteria:
            lines.append("  Acceptance Criteria:")
            for i, criterion in enumerate(req.acceptance_criteria, start=1):
                lines.append(f"    {i}. {criterion}")
    return "\n".join(lines)


def _group_step_ids_by_requirement(plan: List[Step]) -> Dict[str, List[str]]:
    grouped: Dict[str, List[str]] = {}
    for step in plan:
        sid = str(step.id)
        match = re.match(r"^(R\d+)-S\d+$", sid)
        if not match:
            continue
        rid = match.group(1)
        grouped.setdefault(rid, []).append(sid)
    for rid in grouped:
        grouped[rid] = sorted(grouped[rid])
    return grouped


def planner_node(state: AgentState):
    if not state.trigger_plan:
        return {}

    logger.info("[planner_node] start session=%s mode=%s", getattr(state, "session_id", "<unknown>"), state.mode)
    state.current_agent = "planner"

    requirements = state.requirements or []

    if requirements == []:
        requirements_context = get_requirement_from_txt()
    else:
        requirements_context = _build_requirements_context(requirements)

    if not requirements_context:
        logger.warning("[planner_node] no requirements; returning no-op")
        return {
            "trigger_plan": False,
            "interface_refresh": False,
            "current_agent": "planner",
            "messages": state.messages + [{"role": "assistant", "content": "当前没有可规划的需求，请先在聊天中补充需求。"}],
            "plan_status": PlanStatus.DRAFT,
            "run_status": RunStatus.IDLE,
            "approval_required": False,
            "approval_type": None,
            "approval_payload": None,
        }
    llm_messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Requirements:\n{requirements_context}\n\nGenerate plan now.",
        },
    ]

    try:
        response = call_gpt(
            messages=llm_messages,
            tools=None,
            # response_format={"type": "json_object"},
            temperature=0.3,
        )
        content = response["choices"][0]["message"]["content"]
        pprint(f"llm resoibe {content} llm repsonse")
        json_text = extract_json_from_markdown(content)
        data = PlannerOutput.model_validate_json(json_text)
    except Exception as e:
        logger.error("[planner_node] LLM call failed: %s", str(e))
        return {
            "trigger_plan": False,
            "interface_refresh": False,
            "current_agent": NextNode.PLANNER,
            "last_failed_node": NextNode.PLANNER,
            "last_error_message": "规划节点（planner）生成失败。",
            "next_node": NextNode.ERROR,
            "retrying_node": None,
            "progress_text": "当前进度：需求已整理，等待重新生成开发计划。",
            "run_status": RunStatus.BLOCKED,
            "approval_required": False,
            "approval_type": None,
            "approval_payload": None,
        }

    old_plan = {s.id: s for s in (state.plan or [])}
    new_plan: List[Step] = []

    for draft in data.plan:
        if draft.id in old_plan:
            updated_step = old_plan[draft.id].model_copy(update=draft.model_dump())
            new_plan.append(updated_step)
        else:
            new_plan.append(Step(**draft.model_dump()))

    requirement_step_ids = _group_step_ids_by_requirement(new_plan)
    updated_requirements = []
    for req in requirements:
        updated_requirements.append(
            req.model_copy(update={"step_ids": requirement_step_ids.get(req.id, [])})
        )

    logger.info("[planner_node] finished session=%s steps=%d", getattr(state, "session_id", "<unknown>"), len(new_plan))
    return {
        "plan": new_plan,
        "requirements": updated_requirements,
        "current_step": 0,
        "trigger_plan": False,
        "interface_refresh": True,
        "current_agent": NextNode.PLANNER,
        "last_failed_node": None,
        "last_error_message": None,
        "retry_count": 0,
        "retrying_node": None,
        "progress_text": "当前进度：开发计划已生成，正在补全接口定义。",
        "next_node": None,
        "plan_status": PlanStatus.DRAFT,
        "run_status": RunStatus.IDLE,
        "approval_required": False,
        "approval_type": None,
        "approval_payload": None,
    }
