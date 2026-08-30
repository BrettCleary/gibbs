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
    from .activities import execute_calculation, run_campaign


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


@dataclass
class CampaignInput:
    campaign_id: str
    agent_run_id: str
    timeout_seconds: int = 86400
    heartbeat_timeout_seconds: int = 60
    max_attempts: int = 3


@workflow.defn
class RunCampaignWorkflow:
    """The autonomous campaign loop, hosted on the worker instead of the API.

    The loop keeps no state of its own — every decision is rebuilt from the
    database (`build_state`, `_refresh_budget`, and an idempotent `initialize`) —
    so a retry after a worker crash simply resumes from the measurements already
    persisted. That is why the whole loop can be one activity instead of an
    activity per iteration: durability comes from the database, and Temporal only
    has to guarantee the loop is running somewhere.
    """

    @workflow.run
    async def run(self, input: CampaignInput) -> str:
        return await workflow.execute_activity(
            run_campaign,
            args=[input.campaign_id, input.agent_run_id],
            start_to_close_timeout=timedelta(seconds=input.timeout_seconds),
            heartbeat_timeout=timedelta(seconds=input.heartbeat_timeout_seconds),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=5),
                backoff_coefficient=2.0,
                maximum_attempts=input.max_attempts,
            ),
        )
