import json
import logging
import uuid
from datetime import datetime, timezone

from agent.state import AgentState, ToolEvent
from tools.tool_registry import TOOL_MAP

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def _make_tool_event(state: AgentState, tool_name: str, arguments: dict, *, status: str, result=None, error_message=None):
    result_preview = None if result is None else str(result)[:500]
    return ToolEvent(
        id=str(uuid.uuid4()),
        tool_name=tool_name,
        status=status,
        arguments=arguments,
        result_preview=result_preview,
        error_message=error_message,
        created_at=datetime.now(timezone.utc).isoformat(),
        source_agent=state.current_agent.value if getattr(state, "current_agent", None) else None,
        step_id=state.current_step_id,
    )


def tool_node(state: AgentState):
    messages = state.messages
    if not messages:
        return state

    last_message = messages[-1]
    tool_calls = last_message.get("tool_calls", [])

    if not tool_calls:
        return state

    new_messages = []
    tool_events = list(state.tool_events)

    for tool_call in tool_calls:
        tool_name = tool_call["function"]["name"]
        arguments = json.loads(tool_call["function"]["arguments"])
        tool = TOOL_MAP.get(tool_name)

        logger.info("[tool_node] executing tool=%s session=%s", tool_name, getattr(state, "session_id", "<unknown>"))

        if tool is None:
            error_message = f"Unknown tool: {tool_name}"
            result = error_message
            event = _make_tool_event(
                state,
                tool_name,
                arguments,
                status="failed",
                result=result,
                error_message=error_message,
            )
        else:
            try:
                result = tool(**arguments)
                logger.info("[tool_node] tool=%s finished", tool_name)
                event = _make_tool_event(state, tool_name, arguments, status="passed", result=result)
            except Exception as e:
                error_message = str(e)
                result = f"工具执行出错: {error_message}"
                logger.exception("[tool_node] tool=%s raised error", tool_name)
                event = _make_tool_event(
                    state,
                    tool_name,
                    arguments,
                    status="failed",
                    result=result,
                    error_message=error_message,
                )

        tool_events.append(event)
        state.last_tool_event = event
        new_messages.append({
            "role": "tool",
            "tool_call_id": tool_call["id"],
            "content": str(result)
        })

    state.tool_events = tool_events
    state.messages = messages + new_messages
    state.tool_call = None
    return state

    # llm输出格式示例：
#     {
#  "tool_calls": [
#    {
#      "name": "search",
#      "arguments": {
#        "query": "latest AI news"
#      }
#    }
#  ]
# }
