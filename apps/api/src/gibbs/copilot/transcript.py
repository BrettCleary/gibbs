"""Rows <-> Pydantic AI history <-> UI transcript.

The chat is stored relationally (chat -> messages -> tool_call). For each turn
the model's history is rebuilt from those rows, and after the run the new
messages of the run are split back into one assistant row plus its tool calls.
"""

from __future__ import annotations

import json
from typing import Any, Sequence

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from ..db.models import CopilotMessage, CopilotToolCall

MAX_RESULT_CHARS = 4000
FORM_PATCH = "form_patch"


# --------------------------------------------------------------- rows -> history


def history_from_rows(rows: Sequence[CopilotMessage]) -> list[ModelMessage]:
    """Rebuild the model-facing history from the stored timeline.

    An assistant row with tool calls becomes a response carrying the calls, a
    request carrying their returns, then a response carrying the text — the
    same shape the model produced, minus intermediate narration.
    """
    history: list[ModelMessage] = []
    for row in rows:
        if row.role == "user":
            history.append(ModelRequest(parts=[UserPromptPart(content=row.message)]))
            continue
        calls = sorted(row.tool_calls, key=lambda c: (c.position, c.id))
        if calls:
            history.append(
                ModelResponse(
                    parts=[
                        ToolCallPart(tool_name=c.name, args=c.arguments, tool_call_id=c.call_id)
                        for c in calls
                    ]
                )
            )
            returns: list[Any] = []
            for c in calls:
                if c.status == "error":
                    returns.append(
                        RetryPromptPart(content=c.output or "tool failed", tool_name=c.name, tool_call_id=c.call_id)
                    )
                else:
                    returns.append(
                        ToolReturnPart(tool_name=c.name, content=c.output or "", tool_call_id=c.call_id)
                    )
            history.append(ModelRequest(parts=returns))
        if row.message:
            history.append(ModelResponse(parts=[TextPart(content=row.message)]))
    return history


# --------------------------------------------------------------- history -> rows


def split_new_messages(new_messages: Sequence[ModelMessage]) -> tuple[str, list[dict]]:
    """Reduce one run's new messages to (assistant text, ordered tool-call dicts)."""
    text_parts: list[str] = []
    calls: list[dict] = []
    by_id: dict[str, dict] = {}
    for message in new_messages:
        if isinstance(message, ModelResponse):
            for part in message.parts:
                if isinstance(part, TextPart):
                    if part.content.strip():
                        text_parts.append(part.content)
                elif isinstance(part, ToolCallPart):
                    entry = {
                        "call_id": part.tool_call_id,
                        "name": part.tool_name,
                        "arguments": part.args_as_json_str(),
                        "output": None,
                        "status": "pending",
                        "position": len(calls),
                    }
                    calls.append(entry)
                    by_id[part.tool_call_id] = entry
        elif isinstance(message, ModelRequest):
            for part in message.parts:
                if isinstance(part, ToolReturnPart):
                    entry = by_id.get(part.tool_call_id)
                    if entry is not None:
                        content = part.content
                        entry["output"] = content if isinstance(content, str) else json.dumps(content, default=str)
                        entry["status"] = "ok"
                elif isinstance(part, RetryPromptPart) and part.tool_call_id:
                    entry = by_id.get(part.tool_call_id)
                    if entry is not None:
                        entry["output"] = str(part.content)
                        entry["status"] = "error"
    return "\n\n".join(text_parts), calls


# ------------------------------------------------------------- rows -> transcript


def _parse(text: str | None) -> Any:
    if text is None:
        return None
    try:
        value = json.loads(text)
    except ValueError:
        return text
    if len(text) > MAX_RESULT_CHARS:
        return {"truncated": True, "preview": text[:MAX_RESULT_CHARS]}
    return value


def tool_call_part(c: CopilotToolCall) -> dict:
    return {
        "type": "tool",
        "id": c.call_id,
        "name": c.name,
        "args": _parse(c.arguments) or {},
        "result": _parse(c.output) if c.status == "ok" else ({"error": c.output} if c.output else None),
        "ok": None if c.status == "pending" else c.status == "ok",
    }


def transcript_from_rows(rows: Sequence[CopilotMessage]) -> list[dict]:
    """The sidebar's shape: user turns, and assistant turns of tool/patch/text parts."""
    turns: list[dict] = []
    for row in rows:
        if row.role == "user":
            turns.append({"role": "user", "text": row.message})
            continue
        parts: list[dict] = [
            tool_call_part(c) for c in sorted(row.tool_calls, key=lambda c: (c.position, c.id))
        ]
        if row.component_type == FORM_PATCH and row.component_data:
            parts.append({"type": "patch", **row.component_data})
        if row.message:
            parts.append({"type": "text", "text": row.message})
        turns.append({"role": "assistant", "parts": parts, "message_id": row.id})
    return turns
