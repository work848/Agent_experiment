import logging
import re
import os
from typing import Optional

from pprint import pprint
from llm.openai_client import call_gpt
from agent.state import AgentState, StepStatus, Step
from code_indexer.get_workspace_skeleton import get_workspace_skeleton_direct
from tools.write_file_tool import write_file
from tools.read_file import read_file

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────
# System Prompt：告诉 LLM 它的角色是一个编码器
# ────────────────────────────────────────────────────────
CODER_SYSTEM_PROMPT = """\
You are an expert Python developer. Your ONLY job is to write Python code.

CRITICAL RULES:
- You MUST return the complete file content inside a ```python code block
- Do NOT call any tools or functions
- Do NOT attempt to read files, run commands, or access any system
- Do NOT use tool_calls
- Do NOT say "let me check" or "let me look" — you already have all the context you need
- Your ENTIRE response must be ONLY a ```python code block, nothing else
- No explanations, no comments outside the code block

Example response format:
```python
def my_function(a: float, b: float) -> float:
    return a + b
```
"""


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


def _is_already_implemented(step: Step, workspace_skeleton: str) -> bool:
    """
    简单判断步骤里的函数/类是否已经在 workspace skeleton 中出现过。
    通过检查 skeleton 文本中是否有 `def {name}` 或 `class {name}` 来判断。
    """
    if not step.interface:
        return False
    
    func_name = step.interface.name
    # skeleton 里的格式类似: "  λ def func_name(...) | docstring"
    # 或者 "  🏛️ class ClassName(...) | docstring"
    if f"def {func_name}(" in workspace_skeleton:
        return True
    if f"class {func_name}" in workspace_skeleton:
        return True
    return False


def _gather_dependency_context(step: Step, all_steps: list, workspace_root: str) -> str:
    """
    根据步骤的依赖关系，读取依赖 step 对应的源文件，拼接成上下文字符串。
    dependencies 是 step id 列表，指向其他 step。
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
        
        # 如果依赖步骤有 implementation_file，读取它的源代码
        if dep_step.implementation_file:
            try:
                content = read_file(dep_step.implementation_file)
                context_parts.append(
                    f"--- Dependency: Step {dep_id} ({dep_step.description}) ---\n"
                    f"File: {dep_step.implementation_file}\n"
                    f"{content}\n"
                )
            except Exception as e:
                logger.warning("Failed to read dependency file %s: %s", dep_step.implementation_file, e)
        
        # 如果依赖步骤有 interface 信息，也附上接口定义作为参考
        if dep_step.interface:
            iface = dep_step.interface
            params_str = ", ".join(f"{p.name}: {p.type}" for p in iface.parameters)
            context_parts.append(
                f"--- Dependency Interface: {iface.name}({params_str}) -> {iface.return_type} ---\n"
                f"Description: {iface.description}\n"
            )
    
    return "\n".join(context_parts)


def _build_coder_prompt(step: Step, workspace_skeleton: str, dep_context: str) -> str:
    """
    构造发给 LLM 的 User 消息，包含：
    - 项目大纲 (skeleton)
    - 依赖上下文
    - 需要实现的接口规格
    - 目标文件路径
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
### Dependency Code (you may call these)
{dep_context}
"""
    
    prompt += """
### Instructions
Please implement the function according to the specification above.
Return the COMPLETE file content in a ```python code block.
"""
    return prompt


def coder_node(state: AgentState):
    """
    Coder 节点核心逻辑：
    1. 获取 workspace skeleton，明确哪些 func 已经被实现了
    2. 对比 plan，找到第一个还没实现的 PENDING 步骤
    3. 收集该步骤的依赖上下文
    4. 调用 LLM 生成代码
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
        if _is_already_implemented(step, workspace_skeleton):
            logger.info("Step %d (%s) already implemented, marking SUCCESS.", step.id, step.interface.name)
            updated_step = step.model_copy(update={"status": StepStatus.SUCCESS})
            new_plan.append(updated_step)
            implemented_count += 1
            continue

        # 4. 收集依赖上下文
        logger.info("Step %d (%s) — gathering dependency context...", step.id, step.interface.name)
        dep_context = _gather_dependency_context(step, state.plan, state.workspace_root)

        # 5. 构造 prompt 并调用 LLM
        user_prompt = _build_coder_prompt(step, workspace_skeleton, dep_context)
        messages = [
            {"role": "system", "content": CODER_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        try:
            logger.info("Step %d — calling LLM to generate code...", step.id)
            response = call_gpt(messages=messages, tools=None)
            # pprint(response)  # 调试用，看看 LLM 返回了什么
            content = response["choices"][0]["message"]["content"]

            # 6. 提取代码
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
            target_file = step.implementation_file
            if not target_file:
                target_file = f"src/{step.interface.name}.py"
                logger.info("Step %d — no implementation_file specified, using default: %s", step.id, target_file)

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