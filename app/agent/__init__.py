"""Agent module for conversational pricing and margin simulation."""
from .checker import render_fallback_template, validate_agent_text
from .fallback import run_scripted_turn
from .loop import run_agent_turn
from .router import get_budget_status, route_turn
from .service import apply_staged_change, get_staged_change, stream_agent_message
from .tools import (
    tool_ask_user,
    tool_check_inputs,
    tool_compare_runs,
    tool_draft_memo,
    tool_explain_flags,
    tool_explain_run,
    tool_read_inputs,
    tool_run_engine,
    tool_run_pricing,
    tool_run_sulphur_sensitivity,
    tool_snapshot_view,
    tool_stage_change,
)
from .types import (
    AgentEvent,
    AgentEventType,
    AgentMessage,
    AgentState,
    QuestionOption,
    StagedChange,
    ToolFact,
)

__all__ = [
    'stream_agent_message',
    'apply_staged_change',
    'get_staged_change',
    'route_turn',
    'get_budget_status',
    'validate_agent_text',
    'render_fallback_template',
    'run_agent_turn',
    'run_scripted_turn',
    'tool_run_engine',
    'tool_run_pricing',
    'tool_read_inputs',
    'tool_check_inputs',
    'tool_compare_runs',
    'tool_snapshot_view',
    'tool_draft_memo',
    'tool_run_sulphur_sensitivity',
    'tool_stage_change',
    'tool_ask_user',
    'tool_explain_flags',
    'tool_explain_run',
    'AgentEvent',
    'AgentEventType',
    'AgentMessage',
    'AgentState',
    'QuestionOption',
    'StagedChange',
    'ToolFact',
]
