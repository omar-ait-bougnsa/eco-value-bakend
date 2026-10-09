"""Data schemas and types for the agent module."""
from typing import Any, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field

AgentEventType = Literal[
    'step',
    'flag',
    'question',
    'tool',
    'result',
    'change',
    'citation',
    'text',
    'error',
    'done',
]


class BaseAgentSchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra='forbid', allow_inf_nan=False)


class ToolFact(BaseAgentSchema):
    """A verified numerical fact produced by an engine tool.
    The LLM is only permitted to output numbers that match registered facts.
    """
    key: str
    value: float
    unit: str
    label: str


class QuestionOption(BaseAgentSchema):
    """An interactive selectable option chip for user decisions."""
    id: str
    label: str
    sub: Optional[str] = None
    action: Optional[str] = None
    value: Optional[Any] = None


class StagedChange(BaseAgentSchema):
    """A proposed input modification requiring explicit user confirmation."""
    id: str
    simulation_id: str = Field(alias='simulationId')
    base_version: int = Field(alias='baseVersion')
    label: str
    reason: str
    patch: dict[str, Any]
    before: dict[str, Any]
    after: dict[str, Any]
    status: Literal['staged', 'applied', 'dismissed'] = 'staged'


class AgentEvent(BaseAgentSchema):
    """A Server-Sent Event streamed to the frontend UI."""
    id: str
    type: AgentEventType
    payload: dict[str, Any]


class ToolCall(BaseAgentSchema):
    id: str
    name: str
    arguments: dict[str, Any]


class AgentMessage(BaseAgentSchema):
    role: Literal['user', 'assistant', 'system', 'tool']
    content: Optional[str] = None
    tool_calls: Optional[list[ToolCall]] = Field(default=None, alias='toolCalls')
    tool_call_id: Optional[str] = Field(default=None, alias='toolCallId')
    name: Optional[str] = None


class AgentState(BaseAgentSchema):
    """In-memory turn execution state for a simulation."""
    simulation_id: str
    mode: Literal['llm', 'script'] = 'llm'
    messages: list[AgentMessage] = Field(default_factory=list)
    facts: dict[str, ToolFact] = Field(default_factory=dict)
    retries: int = 0
    paused: bool = False
    pause_reason: Optional[Literal['question', 'change']] = None
    pending_options: list[QuestionOption] = Field(default_factory=list)
    staged_change: Optional[StagedChange] = None

