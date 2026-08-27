"""In-process pub/sub used to stream campaign events over SSE.

Persisted AgentEvents are the durable record; this bus only fans live updates
out to connected clients.
"""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from typing import Any, AsyncIterator


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)

    async def publish(self, campaign_id: str, event: dict[str, Any]) -> None:
        for queue in list(self._subscribers.get(campaign_id, ())):
            queue.put_nowait(event)

    async def subscribe(self, campaign_id: str) -> AsyncIterator[dict[str, Any]]:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers[campaign_id].add(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            self._subscribers[campaign_id].discard(queue)


event_bus = EventBus()


def sse_format(event: dict[str, Any]) -> dict[str, str]:
    return {"event": event.get("event_type", "message"), "data": json.dumps(event)}


async def emit_agent_event(
    session,
    campaign_id: str,
    event_type: str,
    agent_run_id: str | None = None,
    **fields,
):
    """Persist an AgentEvent and publish it to live SSE subscribers."""
    from .db.models import AgentEvent

    event = AgentEvent(
        campaign_id=campaign_id, agent_run_id=agent_run_id, event_type=event_type, **fields
    )
    session.add(event)
    await session.commit()
    await event_bus.publish(
        campaign_id,
        {
            "id": event.id,
            "campaign_id": campaign_id,
            "agent_run_id": agent_run_id,
            "event_type": event_type,
            "hypothesis": event.hypothesis,
            "reasoning_summary": event.reasoning_summary,
            "action": event.action,
            "tool_name": event.tool_name,
            "tool_output_reference": event.tool_output_reference,
            "payload": event.payload,
            "created_at": event.created_at.isoformat(),
        },
    )
    return event
