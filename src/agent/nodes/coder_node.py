import logging
from typing import Dict, Optional
from llm.openai_client import call_gpt
from tools.tool_registry import TOOLS
from agent.state import AgentState
from code_indexer.get_workspace_skeleton import get_workspace_skeleton_direct
# 假设你的 StepStatus 定义如下
# from your_module import StepStatus 

logger = logging.getLogger(__name__)

def coder_node(state: AgentState) :
    logger.info("--- CODER NODE STARTING ---")

    # 1. 根据 StepStatus 寻找当前需要执行的任务
    current_step_obj = None
    todo_steps = []
    
    if not state.plan:
        logger.warning("No plan found.")
        return state

    for step in state.plan:
        if step.status == "PENDING" and current_step_obj is None:
            current_step_obj = step
        if step.status == "PENDING":
            todo_steps.append(step)

    # 2. 如果没有待处理的任务，说明计划已完成
    if not current_step_obj:
        logger.info("All steps are completed or no pending steps found.")
        return {"next_agent": "reviewer", "success": True}

    logger.info(f"Targeting Step {current_step_obj.id}: {current_step_obj.description}")

    # 3. 获取工作区快照
    workspace_skeleton = get_workspace_skeleton_direct(state.workspace_root)

    # 4. 构造 System Prompt
    system_prompt = f"""You are a coding AI. Your mission is to implement the plan step by step.
                        Current Workspace Structure:
                        {workspace_skeleton}

                        Available Tools: {[t['function']['name'] for t in TOOLS]}

                        Rules:
                        1. ONLY focus on the task described in the 'Current Step'.
                        2. Use tools to create or modify code.
                        3. If you need more information, use a search or read tool.
                        4. If you need to check work progress, use a workspace skeleton tool
                        """

    
    user_content = f"""### Overall Plan Progress:


### Your Current Task:
**Step {current_step_obj.id}**: {current_step_obj.description}
Target File: {current_step_obj.implementation_file or "Determine based on context"}

Please proceed with the implementation."""

    messages = [
        {"role": "system", "content": system_prompt},
        *state.messages,
        {"role": "user", "content": user_content}
    ]

    try:
        response = call_gpt(messages=messages)
        message = response["choices"][0]["message"]
        
        # 准备返回的更新数据
        new_messages = state.messages + [message]
        
        # 逻辑分支：工具调用 vs 普通文本
        if message.get("tool_calls"):
            # 如果开始调用工具，可以将该步骤状态改为 IN_PROGRESS (可选)
            # current_step_obj.status = "IN_PROGRESS" 
            
            return {
                "messages": new_messages,
                "tool_call": message["tool_calls"],
                "current_agent": "coder",
                "next_agent": "executor"
            }
        else:
            # LLM 没调工具，可能是在解释或者报错
            return {
                "messages": new_messages,
                "current_agent": "coder",
                "next_agent": "planner" # 返回给 planner 确认是否需要调整计划
            }

    except Exception as e:
        logger.error(f"Coder node error: {e}")
        return {"next_agent": "planner"}