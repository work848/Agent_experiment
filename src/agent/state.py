from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class ReportStatus(str, Enum):
    PENDING = "pending"
    FIXED = "fixed"
    CLOSED = "closed"


class PlanStatus(str, Enum):
    DRAFT = "draft"
    CONFIRM = "confirm"
    RUNNING = "running"


class Mode(str, Enum):
    CHAT = "chat"
    PLANNING = "planning"
    EXECUTING = "executing"


class UserAction(str, Enum):
    SAVE_PLAN = "save_plan"
    REGENERATE_PLAN = "regenerate_plan"
    GO_INTERFACE = "go_interface"
    GENERATE_PLAN = "generate_plan"
    CONTINUE_CHAT = "continue_chat"
    MODIFY_PLAN = "modify_plan"


class NextNode(str, Enum):
    CHAT = "chat"
    PLANNER = "planner"
    INTERFACE = "interface"
    CODER = "coder"
    END = "END"


class RequirementStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    BLOCKED = "blocked"


class Parameter(BaseModel):
    name: str
    type: str


class Interface(BaseModel):
    name: str
    parameters: List[Parameter]
    return_type: str
    description: str
    dependencies: List[str] = Field(default_factory=list)

    @field_validator("dependencies", mode="before")
    @classmethod
    def _normalize_dependencies(cls, value):
        if value is None:
            return []
        if isinstance(value, list):
            return [str(v) for v in value]
        return [str(value)]


class Step(BaseModel):
    id: str
    description: str
    interface: Optional[Interface] = None
    implementation_file: Optional[str] = None
    status: StepStatus = StepStatus.PENDING
    retries: int = 0

    @field_validator("id", mode="before")
    @classmethod
    def _normalize_id(cls, value):
        return str(value)


class Requirement(BaseModel):
    id: str
    title: str
    description: str
    acceptance_criteria: List[str] = Field(default_factory=list)
    priority: int = 3
    status: RequirementStatus = RequirementStatus.PENDING
    step_ids: List[str] = Field(default_factory=list)

    @field_validator("id", mode="before")
    @classmethod
    def _normalize_requirement_id(cls, value):
        return str(value)

    @field_validator("step_ids", mode="before")
    @classmethod
    def _normalize_step_ids(cls, value):
        if value is None:
            return []
        if isinstance(value, list):
            return [str(v) for v in value]
        return [str(value)]


class Email(BaseModel):
    thread_id: str
    source: str
    target: str
    content: str
    reply_content: str | None = None
    resume_to: str | None = None
    is_resolved: bool = False


class AgentState(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    session_id: str
    messages: List[Dict] = Field(default_factory=list)
    workspace_root: Optional[str] = None
    plan: Optional[List[Step]] = None
    requirements: List[Requirement] = Field(default_factory=list)

    current_step: int = 0
    mailbox: List[Email] = Field(default_factory=list)

    current_agent: NextNode = NextNode.CHAT
    next_node: NextNode = NextNode.CHAT

    tool_call: Optional[dict] = None
    trigger_plan: bool = False
    interface_refresh: bool = False

    last_user_action: Optional[UserAction] = None
    mode: Mode = Mode.CHAT
    ready_for_plan: bool = False
    suggested_actions: List[Dict] = Field(default_factory=list)

    success: bool = False

    iterations: int = 0
    max_iterations: int = 5


class StepDraft(BaseModel):
    id: str
    description: str
    implementation_file: Optional[str] = None
    dependencies: List[str] = Field(default_factory=list)

    @field_validator("id", mode="before")
    @classmethod
    def _normalize_id(cls, value):
        return str(value)

    @field_validator("dependencies", mode="before")
    @classmethod
    def _normalize_dependencies(cls, value):
        if value is None:
            return []
        if isinstance(value, list):
            return [str(v) for v in value]
        return [str(value)]


class PlannerOutput(BaseModel):
    plan: List[StepDraft]


class InterfaceTask(BaseModel):
    step_id: str
    interface: Interface

    @field_validator("step_id", mode="before")
    @classmethod
    def _normalize_step_id(cls, value):
        return str(value)


class InterfaceDesignOutput(BaseModel):
    interfaces: List[InterfaceTask]
