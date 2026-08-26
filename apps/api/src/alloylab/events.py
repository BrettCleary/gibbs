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
