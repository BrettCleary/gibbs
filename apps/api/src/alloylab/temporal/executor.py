"""Durable job executor: submits calculations as Temporal workflows.

Drop-in replacement for the local JobExecutor (selected with
ALLOYLAB_EXECUTOR=temporal). Live SSE events are still emitted from the API
process; the worker only computes and persists. Cancelling the campaign task
(shutdown) propagates a workflow cancellation to the worker.
"""

from __future__ import annotations

import asyncio
import logging

from ..config import Settings
from ..jobs.executor import (
    emit_job_completed,
    emit_job_started,
    mark_infrastructure_failure,
)
from .workflows import CalculationInput, RunCalculationWorkflow

logger = logging.getLogger(__name__)


class TemporalJobExecutor:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_jobs)
        self._client = None
        self._client_lock = asyncio.Lock()

    async def _get_client(self):
        from temporalio.client import Client

        async with self._client_lock:
            if self._client is None:
                self._client = await Client.connect(self._settings.temporal_address)
        return self._client

    async def run_calculation(self, calculation_id: str) -> str:
        async with self._semaphore:
            client = await self._get_client()
            await emit_job_started(calculation_id)
            handle = await client.start_workflow(
                RunCalculationWorkflow.run,
                CalculationInput(
                    calculation_id=calculation_id,
                    timeout_seconds=self._settings.job_timeout_seconds,
                ),
                id=f"calc-{calculation_id}",
                task_queue=self._settings.temporal_task_queue,
            )
            try:
                await handle.result()
            except asyncio.CancelledError:
                logger.info("cancelling workflow calc-%s", calculation_id)
                await handle.cancel()
                raise
            except Exception as exc:  # noqa: BLE001 — retry policy exhausted / timeout
                logger.warning("workflow calc-%s failed durably: %s", calculation_id, exc)
                await mark_infrastructure_failure(calculation_id, str(exc))
            await emit_job_completed(calculation_id)
            return "DONE"
