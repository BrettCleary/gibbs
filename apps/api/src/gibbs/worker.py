"""Temporal worker: hosts the campaign loop and the calculation activity.

Run alongside the Temporal server and the API:

    temporal server start-dev            # dev server (brew install temporal)
    uv run --package gibbs python -m gibbs.worker

Kill and restart it mid-campaign: in-flight activities are retried on the new
worker and campaigns finish — that is the durability Milestone 7 adds.

With ALLOYLAB_EXECUTOR=temporal the autonomous loop itself lives here rather
than in the API process, so campaigns no longer die when the API container is
recycled. The API only submits the workflow.
"""

from __future__ import annotations

import asyncio
import logging

from temporalio.worker import Worker

from .config import get_settings
from .temporal.activities import execute_calculation, run_campaign
from .temporal.client import connect_temporal_client, describe_target
from .temporal.workflows import RunCalculationWorkflow, RunCampaignWorkflow
from .tracing import setup_tracing, shutdown_tracing

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("gibbs.worker")


async def main() -> None:
    settings = get_settings()
    setup_tracing()
    client = await connect_temporal_client(settings)
    # A campaign activity is held open for the entire run, so its slots are
    # budgeted separately from the calculation slots; sharing one pool would let
    # concurrent campaigns occupy every slot and starve the work they spawn.
    activity_slots = settings.max_concurrent_jobs + settings.max_concurrent_campaigns
    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[RunCalculationWorkflow, RunCampaignWorkflow],
        activities=[execute_calculation, run_campaign],
        max_concurrent_activities=activity_slots,
    )
    logger.info(
        "worker up: temporal=%s queue=%s db=%s jobs=%d campaigns=%d",
        describe_target(settings),
        settings.temporal_task_queue,
        settings.database_url,
        settings.max_concurrent_jobs,
        settings.max_concurrent_campaigns,
    )
    try:
        await worker.run()
    finally:
        shutdown_tracing()


if __name__ == "__main__":
    asyncio.run(main())
