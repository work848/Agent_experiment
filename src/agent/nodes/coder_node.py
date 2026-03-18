import logging
import re
import os
from typing import Optional

from pprint import pprint
from llm.openai_client import call_gpt
from agent.state import AgentState, StepStatus, Step
from code_indexer.get_workspace_skeleton import get_workspace_skeleton_direct
from code_indexer.ast_checker import check_if_implemented
from tools.write_file_tool import write_file
from tools.read_file import read_file
from agent.agent_prompt.coder_prompt import get_coder_system_prompt
logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────
# System Prompt：告诉 LLM 它的角色是一个编码器
# ────────────────────────────────────────────────────────



def _extract_python_code(text: str) -> Optional[str]:
    """从 LLM 返回的 markdown 中提取 python 代码块"""
    # 优先匹配 ```python
    match = re.search(r"```python\s*\n(.*?)```", text, re.S)
    if match:
        return match.group(1).strip()
    # fallback: 匹配普通 ```
    match = re.search(r"```\s*\n(.*?)```", text, re.S)
    if match:
        return match.group(1).strip()
    return None


def _apply_search_replace(original_content: str, response_text: str) -> str:
    """Apply <<<<\nold\n====\nnew\n>>>> search/replace blocks to the text."""
    blocks = re.findall(r"<<<<\n(.*?)\n====\n(.*?)\n>>>>", response_text, flags=re.DOTALL)
    if not blocks:
        return original_content
        
    new_content = original_content
    for old_text, new_text in blocks:
        if old_text in new_content:
            new_content = new_content.replace(old_text, new_text, 1)
        else:
            logger.warning("Could not find the exact old_text block to replace.")
    return new_content


def _is_already_implemented(step: Step, workspace_skeleton: str, workspace_root: str) -> bool:
    """
    Check if the specific function/class is already implemented in the target file.
    """
    if not step.interface:
        return False
        
    target_file = step.implementation_file
    if not target_file:
        return False
        
    # 构建绝对路径
    full_path = os.path.join(workspace_root, target_file) if not os.path.isabs(target_file) else target_file
    return check_if_implemented(full_path, step.interface.name)


def _gather_dependency_context(step: Step, all_steps: list, workspace_root: str) -> str:
    """
    根据步骤的依赖关系，组装依赖的接口签名作为上下文。
    依赖项的完整实现不再被读取，以节省 token 并防止 LLM 困惑。
    """
    if not step.interface or not step.interface.dependencies:
        return ""
    
    # 建立 id -> step 映射
    step_map = {s.id: s for s in all_steps}
    
    context_parts = []
    for dep_id in step.interface.dependencies:
        dep_step = step_map.get(dep_id)
        if not dep_step:
            continue
        
        # 如果依赖步骤有 interface 信息，附上接口定义作为参考
        if dep_step.interface:
            iface = dep_step.interface
            params_str = ", ".join(f"{p.name}: {p.type}" for p in iface.parameters)
            context_parts.append(
                f"--- Dependency Interface: {iface.name}({params_str}) -> {iface.return_type} ---\n"
                f"Description: {iface.description}\n"
            )
    
    return "\n".join(context_parts)


def _build_coder_prompt(step: Step, workspace_skeleton: str, dep_context: str, existing_content: str = None) -> str:
    """
    构造发给 LLM 的 User 消息
    """
    iface = step.interface
    params_str = ", ".join(f"{p.name}: {p.type}" for p in iface.parameters)
    
    prompt = f"""\
## Task: Implement Step {step.id} — {step.description}

### Target File
{step.implementation_file or "You decide the appropriate file path"}

### Interface Specification
- Function name: {iface.name}
- Parameters: {params_str}
- Return type: {iface.return_type}
- Description: {iface.description}

### Project Architecture
{workspace_skeleton}
"""
    if dep_context:
        prompt += f"""
### Dependency Interfaces (Available to call)
{dep_context}
"""
    
    if existing_content is not None:
        prompt += f"""
### Existing File Content
```python
{existing_content}
```

### Instructions
The target file already exists. Please implement the {iface.name} function by specifying SEARCH/REPLACE blocks.
Format your response exactly like this:
<<<<
old lines to remove
====
new lines to insert
>>>>
"""
    else:
        prompt += """
### Instructions
The target file is new. Please implement the function according to the specification above.
Return the COMPLETE file content in a single ```python code block.
"""
    return prompt


def coder_node(state: AgentState):
    """
    Coder 节点核心逻辑：
    1. 获取 workspace skeleton
    2. 对比 plan，找到第一个还没实现的 PENDING 步骤
    3. 收集该步骤的依赖上下文
    4. 调用 LLM 生成代码 (处理 NEW 和 EDIT 两种情形)
    5. 写入文件
    6. 更新状态，继续下一个 PENDING 步骤
    """
    logger.info("--- CODER NODE STARTING ---")
    state.current_agent = "coder"

    if not state.plan:
        logger.warning("No plan found, coder has nothing to do.")
        return {"current_agent": "coder"}

    # 1. 获取 workspace skeleton
    workspace_skeleton = get_workspace_skeleton_direct(state.workspace_root)
    logger.info("Workspace skeleton loaded (%d chars)", len(workspace_skeleton))

    new_plan = []
    implemented_count = 0
    failed_count = 0

    # 2. 遍历 plan 中的每个步骤
    for step in state.plan:
        # 跳过非 PENDING 状态的步骤（已成功或已失败的）
        if step.status != StepStatus.PENDING:
            new_plan.append(step)
            continue

        # 没有 interface 定义的步骤无法实现
        if not step.interface:
            logger.warning("Step %d has no interface definition, skipping.", step.id)
            new_plan.append(step)
            continue

        # 3. 检查是否已经实现了
        if _is_already_implemented(step, workspace_skeleton, state.workspace_root):
            logger.info("Step %d (%s) already implemented, marking SUCCESS.", step.id, step.interface.name)
            updated_step = step.model_copy(update={"status": StepStatus.SUCCESS})
            new_plan.append(updated_step)
            implemented_count += 1
            continue

        # 4. 收集依赖上下文
        logger.info("Step %d (%s) — gathering dependency context...", step.id, step.interface.name)
        dep_context = _gather_dependency_context(step, state.plan, state.workspace_root)

        # 看看目标文件是否存在
        target_file = step.implementation_file
        if not target_file:
            target_file = f"src/{step.interface.name}.py"
            
        full_path = os.path.join(state.workspace_root, target_file) if not os.path.isabs(target_file) else target_file
        existing_content = None
        if os.path.exists(full_path):
            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    existing_content = f.read()
            except Exception as e:
                logger.warning("Failed to read existing file %s: %s", full_path, e)

        # 5. 构造 prompt 并调用 LLM
        user_prompt = _build_coder_prompt(step, workspace_skeleton, dep_context, existing_content)
      

        # 1. 判定现状
        is_new_file = existing_content is None
        is_new_func = True

        if existing_content and f"def {step.interface.name}" in existing_content:
            is_new_func = False

        # 2. 动态分配模式 (Choice 分流)
        if is_new_file:
            # 场景 1: 完全是新文件 -> 全量模式
            choice = 1
        elif is_new_func:
            # 场景 3: 文件在，但函数不在 (Step 3 的情况) -> 全量追加模式
            choice = 3
        else:
            # 场景 2: 文件在，函数也在 -> 增量修改模式
            choice = 2
            
        CODER_SYSTEM_PROMPT = get_coder_system_prompt(choice=choice)
        # 3. 调用时传入这个动态的 prompt
        
        messages = [
            {"role": "system", "content": CODER_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]   
        
        try:
            logger.info("Step %d — calling LLM to generate code...", step.id)
            response = call_gpt(messages=messages, tools=None, temperature=0.1)
            content = response["choices"][0]["message"]["content"]
            logger.info("Step %d — LLM Content:\n%s", step.id, content)

            code = None
            if existing_content is not None:
                # 增量修改模式
                code = _apply_search_replace(existing_content, content)
                if code == existing_content and "<<<<" not in content:
                    logger.warning("Step %d — LLM did not return a valid patch block, or patch failed.", step.id)
                    fallback_code = _extract_python_code(content)
                    if fallback_code:
                        code = fallback_code
                        logger.info("Step %d — Falling back to full python rewrite.", step.id)
                    else:
                        updated_step = step.model_copy(update={
                            "status": StepStatus.FAILED,
                            "retries": step.retries + 1,
                        })
                        new_plan.append(updated_step)
                        failed_count += 1
                        continue
            else:
                # 全新文件模式
                code = _extract_python_code(content)
                if not code:
                    logger.error("Step %d — LLM did not return a valid python code block.", step.id)
                    updated_step = step.model_copy(update={
                        "status": StepStatus.FAILED,
                        "retries": step.retries + 1,
                    })
                    new_plan.append(updated_step)
                    failed_count += 1
                    continue

            # 7. 写入文件
            result = write_file(path=target_file, content=code)
            logger.info("Step %d — write_file result: %s", step.id, result)

            if "successfully" in result.lower():
                updated_step = step.model_copy(update={
                    "status": StepStatus.SUCCESS,
                    "implementation_file": target_file,
                })
                new_plan.append(updated_step)
                implemented_count += 1

                # 刷新 skeleton，后续步骤能基于最新状态判断
                workspace_skeleton = get_workspace_skeleton_direct(state.workspace_root)
            else:
                logger.error("Step %d — write_file failed: %s", step.id, result)
                updated_step = step.model_copy(update={
                    "status": StepStatus.FAILED,
                    "retries": step.retries + 1,
                })
                new_plan.append(updated_step)
                failed_count += 1

        except Exception as e:
            logger.error("Step %d — exception during code generation: %s", step.id, str(e))
            updated_step = step.model_copy(update={
                "status": StepStatus.FAILED,
                "retries": step.retries + 1,
            })
            new_plan.append(updated_step)
            failed_count += 1

    logger.info("--- CODER NODE FINISHED — implemented: %d, failed: %d ---", implemented_count, failed_count)

    return {
        "plan": new_plan,
        "current_agent": "coder",
    }