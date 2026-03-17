from typing import TypedDict, List, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional
from typing import Dict

from enum import Enum

from code_indexer.workspace_models import Workspace
from config.workspace_config import WORKSPACE
# 定义状态枚举
class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"  # 建议增加一个“运行中”，方便追踪
    SUCCESS = "success"
    FAILED = "failed"
class ReportStatus(str, Enum):
    PENDING = "pending"
    FIXED = "fixed"
    CLOSED = "closed"

class Parameter(BaseModel):

    name: str
    type: str


class Interface(BaseModel):

    name: str

    parameters: List[Parameter]

    return_type: str

    description: str
    
    dependencies: List[int] = Field(default_factory=list)

class Step(BaseModel):

    id: int

    description: str

    interface: Optional[Interface] = None

    implementation_file: Optional[str] = None
    
    # dependencies: List[int] = []

    status: StepStatus = StepStatus.PENDING
    
    retries: int = 0
    
class Email(BaseModel):
    thread_id: str
    source: str
    target: str

    content: str
    reply_content: str | None = None

    resume_to: str | None = None

    is_resolved: bool = False
# 这个类是整个 Agent 的核心状态管理类，包含了会话 ID、消息历史、扫描的代码库上下文、开发计划等信息
class AgentState(BaseModel):
    model_config = ConfigDict(
        arbitrary_types_allowed=True
    )
    session_id: str
    
    # 默认空列表，不需要手动初始化
    messages: List[Dict] = Field(default_factory=list)

    # 代码库根路径，方便后续扫描和更新  
    workspace_root: str = WORKSPACE
    # 开发计划，Step 也是 BaseModel
    plan: Optional[List[Step]] = None

    # 当前执行到第几步
    current_step: int = 0

    # 这个邮箱是用来存储 LLM 之间的沟通内容的，方便后续分析和回溯
    mailbox: List[Email] = Field(default_factory=list)
    
    current_agent: str = "planner"  # 当前负责执行的 agent
    # 这个字段是为了让中央调度员知道下一步应该唤起哪个节点的，避免在节点内部写死调用关系
    next_agent: str ="planner"
    
    # 存储 LLM 决定调用的工具信息
    tool_call: Optional[dict] = None

    # 测试是否通过
    success: bool = False
    
    # 迭代计数
    iterations: int = 0
    max_iterations: int = 5

# 这个类部分更新是为了让 palnnerLLM 专注于输出它最擅长的内容：开发计划
class StepDraft(BaseModel):
    id: int

    description: str

    implementation_file: Optional[str] = None
    
    dependencies: List[int] = []
class PlannerOutput(BaseModel):
    # 我们只要求模型返回它最擅长的：开发计划
    plan: List[StepDraft]


# 这个类是 interface_build_node 的输出格式，包含了每个步骤的接口设计信息
class InterfaceTask(BaseModel):
    step_id: int
    interface: Interface  # 使用你之前定义的 Interface 模型


class InterfaceDesignOutput(BaseModel):
    interfaces: List[InterfaceTask]