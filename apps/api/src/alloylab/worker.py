"""Temporal worker: hosts the calculation activity and workflow.

Run alongside the Temporal server and the API:

    temporal server start-dev            # dev server (brew install temporal)
    uv run --package alloylab python -m alloylab.worker

Kill and restart it mid-campaign: in-flight activities are retried on the new
worker and campaigns finish — that is the durability Milestone 7 adds.
"""

from __future__ import annotations

import asyncio
import logging

from temporalio.client import Client
from temporalio.worker import Worker

from .config import get_settings
from .temporal.activities import execute_calculation
from .temporal.workflows import RunCalculationWorkflow

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("alloylab.worker")


async def main() -> None:
    settings = get_settings()
    client = await Client.connect(settings.temporal_address)
    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[RunCalculationWorkflow],
        activities=[execute_calculation],
        max_concurrent_activities=settings.max_concurrent_jobs,
    )
    logger.info(
        "worker up: temporal=%s queue=%s db=%s max_concurrent=%d",
        settings.temporal_address,
        settings.temporal_task_queue,
        settings.database_url,
        settings.max_concurrent_jobs,
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
