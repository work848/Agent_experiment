from enum import Enum
from typing import Any, Dict, List, Optional

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


class GoalStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class PlanStatus(str, Enum):
    DRAFT = "draft"
    READY = "ready"
    APPROVED = "approved"
    SUPERSEDED = "superseded"


class RunStatus(str, Enum):
    IDLE = "idle"
    WAITING_APPROVAL = "waiting_approval"
    RUNNING = "running"
    BLOCKED = "blocked"
    FAILED = "failed"
    SUCCESS = "success"


class StepOutcome(str, Enum):
    SUCCESS = "success"
    RETRY = "retry"
    WAITING_APPROVAL = "waiting_approval"
    BLOCKED = "blocked"
    FAILED = "failed"


class ValidationStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"


class FailureCategory(str, Enum):
    MISSING_IMPLEMENTATION = "missing_implementation"
    MISSING_FILE = "missing_file"
    INVALID_TARGET = "invalid_target"
    EXECUTION_ERROR = "execution_error"
    UNKNOWN = "unknown"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"


class ActionGateType(str, Enum):
    NONE = "none"
    APPROVAL_REQUIRED = "approval_required"
    RISK_REVIEW_REQUIRED = "risk_review_required"
    AWAITING_RESOLUTION = "awaiting_resolution"


class ApprovalType(str, Enum):
    EXECUTE_PLAN = "execute_plan"
    STEP_CHANGE = "step_change"
    RUN_COMMAND = "run_command"
    RETRY_AFTER_FAILURE = "retry_after_failure"


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
    EXECUTE_PLAN = "execute_plan"


class NextNode(str, Enum):
    CHAT = "chat"
    PLANNER = "planner"
    INTERFACE = "interface"
    CODER = "coder"
    TESTER = "tester"
    ERROR = "error"
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
    extra_interfaces: List[Interface] = Field(default_factory=list)
    implementation_file: Optional[str] = None
    test_file: Optional[str] = None
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


class Goal(BaseModel):
    id: str
    title: str
    description: str = ""
    status: GoalStatus = GoalStatus.PENDING
    success_criteria: List[str] = Field(default_factory=list)


class ActionGate(BaseModel):
    type: ActionGateType
    message: Optional[str] = None
    reference_id: Optional[str] = None


class ApprovalRequest(BaseModel):
    id: str
    type: ApprovalType
    title: str
    description: str
    created_at: Optional[str] = None
    step_id: Optional[str] = None
    blocking: bool = True
    payload: Dict[str, Any] = Field(default_factory=dict)
    status: ApprovalStatus = ApprovalStatus.PENDING
    requested_action: Optional[str] = None
    reason: Optional[str] = None
    resolved_at: Optional[str] = None
    resolution_note: Optional[str] = None


class RiskAction(BaseModel):
    id: str
    type: str
    title: str
    description: str
    step_id: Optional[str] = None
    status: str = "pending"
    payload: Dict[str, Any] = Field(default_factory=dict)
    requested_action: Optional[str] = None
    reason: Optional[str] = None


class EvidenceRecord(BaseModel):
    kind: str
    summary: str
    passed: Optional[bool] = None
    file_path: Optional[str] = None
    symbol_name: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)


class ToolEvent(BaseModel):
    id: str
    tool_name: str
    status: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    result_preview: Optional[str] = None
    error_message: Optional[str] = None
    created_at: Optional[str] = None
    source_agent: Optional[str] = None
    step_id: Optional[str] = None


class ValidationSummary(BaseModel):
    status: ValidationStatus
    summary: str
    failure_category: Optional[FailureCategory] = None
    evidence: List[EvidenceRecord] = Field(default_factory=list)


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
    current_step_id: Optional[str] = None
    current_step_title: Optional[str] = None
    mailbox: List[Email] = Field(default_factory=list)

    current_agent: NextNode = NextNode.CHAT
    next_node: Optional[NextNode] = None

    tool_call: Optional[dict] = None
    tool_events: List[ToolEvent] = Field(default_factory=list)
    last_tool_event: Optional[ToolEvent] = None
    trigger_plan: bool = False
    interface_refresh: bool = False

    last_user_action: Optional[UserAction] = None
    mode: Mode = Mode.CHAT
    ready_for_plan: bool = False
    suggested_actions: List[Dict] = Field(default_factory=list)

    last_failed_node: Optional[NextNode] = None
    last_error_message: Optional[str] = None
    retry_count: int = 0
    max_node_retries: int = 1
    retrying_node: Optional[str] = None
    progress_text: Optional[str] = None
    last_action_summary: Optional[str] = None
    last_validation_summary: Optional[str] = None
    last_validation_status: Optional[ValidationStatus] = None
    last_validation_passed: Optional[bool] = None
    last_failure_category: Optional[FailureCategory] = None
    last_evidence: List[EvidenceRecord] = Field(default_factory=list)
    last_outcome: Optional[StepOutcome] = None

    success: bool = False

    iterations: int = 0
    max_iterations: int = 5

    # --- product-state fields (AGENT_FIRST_WORKFLOW) ---
    goal: Optional[Goal] = None
    plan_status: PlanStatus = PlanStatus.DRAFT
    run_id: Optional[str] = None
    run_status: RunStatus = RunStatus.IDLE
    approval_required: bool = False
    approval_type: Optional[ApprovalType] = None
    approval_payload: Optional[Dict[str, Any]] = None
    pending_approvals: List[ApprovalRequest] = Field(default_factory=list)
    risk_actions: List[RiskAction] = Field(default_factory=list)
    action_gate: Optional[ActionGate] = None
    run_summary: Optional[str] = None
    last_saved_at: Optional[str] = None
    last_restored_at: Optional[str] = None
    persisted_file: Optional[str] = None
    restored_from_disk: bool = False
    updated_at: Optional[str] = None


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
    extra_interfaces: List[Interface] = Field(default_factory=list)

    @field_validator("step_id", mode="before")
    @classmethod
    def _normalize_step_id(cls, value):
        return str(value)


class InterfaceDesignOutput(BaseModel):
    interfaces: List[InterfaceTask]
