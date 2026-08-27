"""Temporal activities: the durable compute units that run on worker processes.

The activity delegates to the same `execute_and_persist` the local executor
uses, with a background heartbeat so a dead worker is detected quickly and the
activity is retried on a live one. Scientific failures return normally as
FAILED rows (data for the agent); only infrastructure trouble raises.
"""

from __future__ import annotations

import asyncio

from temporalio import activity

HEARTBEAT_INTERVAL_S = 10.0


@activity.defn
async def execute_calculation(calculation_id: str) -> str:
    from ..jobs.executor import execute_and_persist

    async def _heartbeat_loop() -> None:
        while True:
            activity.heartbeat(calculation_id)
            await asyncio.sleep(HEARTBEAT_INTERVAL_S)

    heartbeat_task = asyncio.create_task(_heartbeat_loop())
    try:
        return await execute_and_persist(calculation_id)
    finally:
        heartbeat_task.cancel()
