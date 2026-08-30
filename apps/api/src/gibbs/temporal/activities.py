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


CAMPAIGN_HEARTBEAT_INTERVAL_S = 15.0


@activity.defn
async def run_campaign(campaign_id: str, agent_run_id: str) -> str:
    """Host the autonomous campaign loop on the worker.

    Previously this ran as a bare asyncio task inside the API process, where a
    container recycle cancelled it mid-iteration and left the campaign RUNNING
    forever with no event written.
    """
    # Imported inside the activity: the workflow sandbox re-imports this module,
    # and gibbs.agent.loop reaches the problem adapters -> icet/spglib, which
    # cannot be loaded twice per process (see this package's __init__).
    from ..agent.loop import run_campaign_loop
    from ..config import get_settings
    from ..jobs.executor import JobExecutor

    async def _heartbeat_loop() -> None:
        while True:
            activity.heartbeat(campaign_id)
            await asyncio.sleep(CAMPAIGN_HEARTBEAT_INTERVAL_S)

    # Deliberately the in-process executor rather than TemporalJobExecutor: we
    # are already on the worker. Running each calculation as its own workflow
    # would need a second activity slot per campaign, so concurrent campaigns
    # could hold every slot waiting for calculation slots that never open.
    executor = JobExecutor(max_concurrent=get_settings().max_concurrent_jobs)
    heartbeat_task = asyncio.create_task(_heartbeat_loop())
    try:
        await run_campaign_loop(campaign_id, agent_run_id, executor)
        return "DONE"
    finally:
        heartbeat_task.cancel()
