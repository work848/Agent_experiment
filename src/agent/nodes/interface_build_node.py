import json
from typing import List, Dict
from llm.openai_client import call_gpt
from agent.state import InterfaceDesignOutput, AgentState, StepStatus
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

Return JSON only.
"""


def interface_node(state: AgentState):
    """
    1. 将输入的 Dict 转换为 AgentState 对象
    2. 使用点符号 (.) 访问属性和 Pydantic V2 的 model_copy 方法
    3. 返回时将对象转回 Dict
    """
    print("PLAN STEPS:")
    # for s in state.plan:
    #     print(s)
    steps_to_design = [
        s for s in state.plan 
        if s.interface is None and s.status == StepStatus.PENDING
    ]

    if not steps_to_design:
        # 无需变动，直接返回空字典（表示不更新状态）
        return {} 

    # 2️⃣ 获取上下文并调用 LLM
    skeleton_context = get_workspace_skeleton_direct(state.workspace_root)

    # 3️⃣ 构造 prompt (Pydantic 对象在 f-string 中会自动调用 __str__)
    llm_messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Workspace structure:\n{skeleton_context}\n\nSteps:\n{steps_to_design}\n\nDesign interfaces."
        }
    ]

    # 4️⃣ 调用 LLM
    response = call_gpt(messages=llm_messages, tools=None)
    content = response["choices"][0]["message"]["content"]
    # print(json.dumps(response, indent=2, ensure_ascii=False, default=str))
    json_text = extract_json(content)
    
    # 验证并解析 LLM 输出
    design_data = InterfaceDesignOutput.model_validate_json(json_text)
    # print("LLM returned interface design:", design_data)

    # 5️⃣ 增量更新 (在对象层面操作)
    # 创建一个 ID 到 interface 对象的映射
    design_map = {item.step_id: item.interface for item in design_data.interfaces}

    new_plan = []

    for step in state.plan:
        if step.id in design_map:
            # 更新 interface 并返回新对象
            new_step = step.model_copy(
            update={"interface": design_map[step.id]}
        )
        else:
             new_step = step
        new_plan.append(new_step)

    # 4️⃣ 返回更新：只返回变动的部分
    # LangGraph 会自动把这些值 update 到全局 state 中
    return {
        "plan": new_plan,
        "current_agent": "interface"
    }