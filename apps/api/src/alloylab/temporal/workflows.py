"""The durable calculation workflow (plan section 11):

    Agent -> Scientific Job API -> Temporal Workflow -> Worker -> engine

One workflow per calculation. The activity retry policy covers INFRASTRUCTURE
failures only (worker death, heartbeat loss, timeout); scientific failures are
persisted as FAILED rows by the activity and complete the workflow normally.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from .activities import execute_calculation


@dataclass
class CalculationInput:
    calculation_id: str
    timeout_seconds: int = 1800
    heartbeat_timeout_seconds: int = 60
    max_attempts: int = 3


@workflow.defn
class RunCalculationWorkflow:
    @workflow.run
    async def run(self, input: CalculationInput) -> str:
        return await workflow.execute_activity(
            execute_calculation,
            input.calculation_id,
            start_to_close_timeout=timedelta(seconds=input.timeout_seconds),
            heartbeat_timeout=timedelta(seconds=input.heartbeat_timeout_seconds),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=2),
                backoff_coefficient=2.0,
                maximum_attempts=input.max_attempts,
            ),
        )
