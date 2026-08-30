"""Persisted AgentEvents are the durable record and the only event transport.

There used to be an in-process pub/sub here that the SSE endpoint subscribed to.
That worked only while the campaign loop ran inside the API process; the loop now
runs in the Temporal worker, so a bus in this process would never see its events.
The SSE endpoint polls `agent_events` instead (see `api/campaigns.stream_events`).
"""

from __future__ import annotations

import json
from typing import Any


def event_payload(event) -> dict[str, Any]:
    """The wire shape of one AgentEvent. Shared by the SSE stream and any other
    consumer so the live feed and the REST history cannot drift apart."""
    return {
        "id": event.id,
        "campaign_id": event.campaign_id,
        "agent_run_id": event.agent_run_id,
        "event_type": event.event_type,
        "hypothesis": event.hypothesis,
        "reasoning_summary": event.reasoning_summary,
        "action": event.action,
        "tool_name": event.tool_name,
        "tool_output_reference": event.tool_output_reference,
        "payload": event.payload,
        "created_at": event.created_at.isoformat(),
    }


def sse_format(event: dict[str, Any]) -> dict[str, str]:
    return {"event": event.get("event_type", "message"), "data": json.dumps(event)}


async def emit_agent_event(
    session,
    campaign_id: str,
    event_type: str,
    agent_run_id: str | None = None,
    **fields,
):
    """Persist an AgentEvent. Readers pick it up from the database."""
    from .db.models import AgentEvent

    event = AgentEvent(
        campaign_id=campaign_id, agent_run_id=agent_run_id, event_type=event_type, **fields
    )
    session.add(event)
    await session.commit()
    return event
