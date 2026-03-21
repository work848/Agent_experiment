import json
import logging
from pprint import pprint
from llm.openai_client import call_gpt
import re
from agent.state import AgentState, PlannerOutput, Step
logger = logging.getLogger(__name__)


schema = json.dumps(PlannerOutput.model_json_schema(), indent=2)
SYSTEM_PROMPT = f"""
You are a software architect.

Your job is to create a development plan by python to implement the user's request. 

The plan must be a valid JSON object wrapped in a markdown code block.
Structure your response as follows:
{schema}
IMPORTANT RULES:
- DO NOT call any tools
- DO NOT access files
- DO NOT attempt to read uploads
- Only return structured interface definitions

Return JSON only.
"""

def extract_json_from_markdown(text: str) -> str:
    """
    从 LLM 返回的 markdown 中提取 JSON
    支持：
    - ```json code block
    - ``` code block
    - 普通 { } JSON
    """
    

    # 1️⃣ 优先匹配 ```json code block
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.S)
    if match:
        return match.group(1)

    # 2️⃣ 匹配普通 ``` code block
    match = re.search(r"```\s*(\{.*?\})\s*```", text, re.S)
    if match:
        return match.group(1)

    # 3️⃣ fallback：直接找 {}
    match = re.search(r"\{.*\}", text, re.S)
    if match:
        return match.group()

    raise ValueError("No valid JSON found in response")

def planner_node(state):    
    
    if not state.trigger_plan:
        return {}

    logger.info("Planner node started")
    state.current_agent = "planner"  # 明确当前节点身份，方便调度员决策
    messages = messages = state.messages

    
    # schema = {
    #     "type": "json_schema",
    #     "json_schema": {
    #         "name": "planner_output",
    #         "strict": True, # 开启严格模式
    #         "schema": PlannerOutput.model_json_schema()
    #     }
    # }
    
    llm_messages = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ] + messages[-6:]

    try:
        response = call_gpt(
            messages=llm_messages,
            tools=None)

        content = response["choices"][0]["message"]["content"]
        # pprint(f"planner  Response: {json.dumps(response, indent=2, ensure_ascii=False, default=str)}")
        json_text = extract_json_from_markdown(content)
        data = PlannerOutput.model_validate_json(json_text)

    except Exception as e:
        logger.error("LLM call failed in planner node: %s", str(e))
        raise
    # 3. --- 核心：增量更新，防止 retries 等参数归零 ---
    old_plan = {s.id: s for s in (state.plan or [])}
    new_plan = []
    
    for draft in data.plan:
        if draft.id in old_plan:
            # 如果 ID 存在，我们只更新 LLM 关心的字段
            # 使用 model_copy(update=...) 会保留 status, retries 等原有字段
            updated_step = old_plan[draft.id].model_copy(update=draft.model_dump())
            new_plan.append(updated_step)
        else:
            # 如果是全新的 ID，直接创建新的 Step
            new_plan.append(Step(**draft.model_dump()))

    # 4. 返回更新后的状态
    
    logger.info("Planner node finished")
    return {
        "plan": new_plan,
        "current_step": 0, # 通常重新规划后从第 0 步开始，也可以根据逻辑自定
        "trigger_plan": False, # 规划完成后重置触发标志，由调度员控制何时再次触发
        "interface_refresh": True,
    }


