import json
import re
from typing import Dict, List

from pydantic import BaseModel, Field
from pprint import pprint
from llm.openai_client_normal import call_gpt
from llm.llm_requirements_client import call_gpt_requirements
from agent.state import AgentState, Mode, NextNode, Requirement, RequirementStatus


CTA_ACTIONS = [
    {"action": "generate_plan", "label": "生成计划"},
    {"action": "continue_chat", "label": "继续补充"},
]


class ExtractedRequirement(BaseModel):
    title: str
    description: str
    acceptance_criteria: List[str] = Field(default_factory=list)
    priority: int = 3


class RequirementExtractionOutput(BaseModel):
    requirements: List[ExtractedRequirement] = Field(default_factory=list)


def _extract_json_from_markdown(text: str) -> str:
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.S)
    if match:
        return match.group(1)
    match = re.search(r"```\s*(\{.*?\})\s*```", text, re.S)
    if match:
        return match.group(1)
    match = re.search(r"\{.*\}", text, re.S)
    if match:
        return match.group()
    raise ValueError("No valid JSON found")


def _is_ready_for_plan(messages):
    last_user = ""
    for m in reversed(messages):
        if isinstance(m, dict) and m.get("role") == "user":
            last_user = str(m.get("content") or "").strip()
            break

    if not last_user:
        return False

    keywords = ["implment app"]
    if len(last_user) >= 20:
        return True
    return any(k in last_user.lower() for k in keywords)


def _normalize_text(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def _requirement_key(title: str, description: str) -> str:
    return f"{_normalize_text(title)}|{_normalize_text(description)}"


def _next_requirement_id(existing_ids: List[str]) -> str:
    max_num = 0
    for rid in existing_ids:
        match = re.match(r"^R(\d+)$", str(rid or ""))
        if match:
            max_num = max(max_num, int(match.group(1)))
    return f"R{max_num + 1:03d}"


def _extract_requirements(messages: List[Dict]) -> List[ExtractedRequirement]:
    schema = json.dumps(RequirementExtractionOutput.model_json_schema(), ensure_ascii=False, indent=2)
    system_prompt = f"""
        you are an expert requirement analysis product requirements from conversation.
        Return only JSON, matching this schema exactly:
        {schema}

        if you cant output json format, the output i cant do it
        Rules:
        - Return normalized requirements without IDs.
        - title should be concise.
        - description should be specific and actionable.
        - acceptance_criteria should be concrete and testable.
        - priority range is 1 (highest) to 5 (lowest).
        """

    response = call_gpt_requirements(
        messages=[{"role": "system", "content": system_prompt}] + messages[-8:],
        temperature=0.7,
    )
    content = response["choices"][0]["message"]["content"]
    pprint(f"requirement:{content}")
    json_text = _extract_json_from_markdown(content)
    parsed = RequirementExtractionOutput.model_validate_json(json_text)
    return parsed.requirements


def _reconcile_requirements(existing: List[Requirement], extracted: List[ExtractedRequirement]) -> List[Requirement]:
    existing_by_key = {_requirement_key(r.title, r.description): r for r in existing}
    all_ids = [r.id for r in existing]

    reconciled: List[Requirement] = []
    for item in extracted:
        key = _requirement_key(item.title, item.description)
        matched = existing_by_key.get(key)

        if matched:
            reconciled.append(
                matched.model_copy(
                    update={
                        "title": item.title.strip() or matched.title,
                        "description": item.description.strip() or matched.description,
                        "acceptance_criteria": [c.strip() for c in item.acceptance_criteria if c and c.strip()],
                        "priority": item.priority if 1 <= int(item.priority) <= 5 else matched.priority,
                    }
                )
            )
            continue
        pprint(f"提取的需求{extracted}")
        new_id = _next_requirement_id(all_ids)
        all_ids.append(new_id)
        reconciled.append(
            Requirement(
                id=new_id,
                title=item.title.strip(),
                description=item.description.strip(),
                acceptance_criteria=[c.strip() for c in item.acceptance_criteria if c and c.strip()],
                priority=item.priority if 1 <= int(item.priority) <= 5 else 3,
                status=RequirementStatus.PENDING,
                step_ids=[],
            )
        )

    return reconciled


def _build_fallback_requirement(messages: List[Dict], existing_ids: List[str]) -> Requirement:
    last_user = ""
    for m in reversed(messages):
        if isinstance(m, dict) and m.get("role") == "user":
            last_user = str(m.get("content") or "").strip()
            break

    text = last_user or "User provided app requirements"
    title = text.split("\n", 1)[0][:30].strip() or "Core requirement"
    description = text[:500]

    return Requirement(
        id=_next_requirement_id(existing_ids),
        title=title,
        description=description,
        acceptance_criteria=["Generate an initial executable plan from this requirement"],
        priority=2,
        status=RequirementStatus.PENDING,
        step_ids=[],
    )


def chat_node(state: AgentState):
    messages = state.messages
    user_message_count = sum(
        1 for m in messages if isinstance(m, dict) and m.get("role") == "user"
    )

    ready_for_plan = _is_ready_for_plan(messages)
    extraction_ready = user_message_count >= 3 or ready_for_plan

    was_ready_for_plan = bool(state.ready_for_plan)

    requirements = state.requirements or []
    pprint(f"{requirements}")
    if extraction_ready:
        try:
            extracted = _extract_requirements(messages)
            requirements = _reconcile_requirements(requirements, extracted)
        except Exception:
            requirements = requirements

    if ready_for_plan and not requirements:
        fallback = _build_fallback_requirement(messages, [r.id for r in requirements])
        requirements = requirements + [fallback]

    if state.mode == Mode.CHAT and ready_for_plan:
        return {
            "ready_for_plan": True,
            "suggested_actions": CTA_ACTIONS,
            "mode": Mode.PLANNING,
            "trigger_plan": True,
            "next_node": NextNode.PLANNER,
            "requirements": requirements,
        }

    system_prompt = """
You are a product manager.

Your job is to:
- Understand the user's requirements
- Ask clarifying questions
- Suggest improvements
- Help refine the idea BEFORE planning

DO NOT generate implementation plans.
DO NOT output JSON.
Just chat naturally.
DO NOT tell user that I have  I can see you uploaded a file.
"""

    response = call_gpt(
        messages=[{"role": "system", "content": system_prompt}] + messages[-10:],
        tools=None,
        temperature=0.7,
    )

    reply = response["choices"][0]["message"]["content"]

    if ready_for_plan and not was_ready_for_plan:
        reply = "需求信息已经足够完整。下一次请求我会自动进入规划并生成计划。"

    updated_messages = messages + [{"role": "assistant", "content": reply}]

    return {
        "messages": updated_messages,
        "ready_for_plan": ready_for_plan,
        "suggested_actions": CTA_ACTIONS if ready_for_plan else [],
        "requirements": requirements,
    }
