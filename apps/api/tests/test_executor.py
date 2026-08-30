"""Milestone 7 unit tests: executor selection, idempotent durable unit,
infrastructure-failure marking."""

import os

import pytest

from gibbs.config import Settings
from gibbs.jobs import JobExecutor, create_executor
from gibbs.jobs.executor import (
    execute_and_persist,
    mark_infrastructure_failure,
)


def test_create_executor_local_default():
    assert isinstance(create_executor(Settings()), JobExecutor)


def test_create_executor_temporal():
    from gibbs.temporal import TemporalJobExecutor

    executor = create_executor(Settings(executor="temporal"))
    assert isinstance(executor, TemporalJobExecutor)


async def _make_ising_calc(client) -> str:
    r = await client.post(
        "/campaigns", json={"name": "exec", "strategy": "grid", "lattice_size": 8}
    )
    campaign_id = r.json()["id"]
    from gibbs.db.base import get_session_factory
    from gibbs.db.models import Calculation

    async with get_session_factory()() as session:
        calc = Calculation(
            campaign_id=campaign_id,
            calculation_type="MONTE_CARLO",
            input_parameters={
                "temperature": 2.2,
                "lattice_size": 8,
                "n_equilibration_sweeps": 50,
                "n_measurement_sweeps": 100,
                "seed": 1,
            },
        )
        session.add(calc)
        await session.flush()
        calc_id = calc.id
        await session.commit()
    return calc_id


async def test_execute_and_persist_is_idempotent(client):
    calc_id = await _make_ising_calc(client)
    assert await execute_and_persist(calc_id) == "SUCCEEDED"

    from gibbs.db.base import get_session_factory
    from gibbs.db.models import Calculation

    async with get_session_factory()() as session:
        calc = await session.get(Calculation, calc_id)
        first_output = dict(calc.output)
        completed_at = calc.completed_at

    # Replay (e.g. a Temporal activity retry after a crash) must be a no-op.
    assert await execute_and_persist(calc_id) == "SUCCEEDED"
    async with get_session_factory()() as session:
        calc = await session.get(Calculation, calc_id)
        assert calc.output == first_output
        assert calc.completed_at == completed_at


async def test_mark_infrastructure_failure(client):
    calc_id = await _make_ising_calc(client)
    await mark_infrastructure_failure(calc_id, "worker vanished")

    from gibbs.db.base import get_session_factory
    from gibbs.db.models import Calculation

    async with get_session_factory()() as session:
        calc = await session.get(Calculation, calc_id)
        assert calc.status == "FAILED"
        assert calc.failure_category == "INFRASTRUCTURE_FAILURE"

    # Never clobbers a terminal state.
    await mark_infrastructure_failure(calc_id, "again")
    async with get_session_factory()() as session:
        calc = await session.get(Calculation, calc_id)
        assert calc.failure_metadata["error"] == "worker vanished"


@pytest.mark.skipif(
    not os.environ.get("ALLOYLAB_TEMPORAL_TEST"),
    reason="set ALLOYLAB_TEMPORAL_TEST=1 to run the full Temporal round trip "
    "(downloads a local test server on first use)",
)
async def test_temporal_round_trip_campaign(client, monkeypatch):
    """A full ising campaign where every calculation runs as a Temporal
    workflow activity on an in-test worker."""
    import asyncio

    from temporalio.testing import WorkflowEnvironment
    from temporalio.worker import UnsandboxedWorkflowRunner, Worker

    from gibbs.agent.loop import runner_registry
    from gibbs.config import Settings
    from gibbs.temporal import TemporalJobExecutor
    from gibbs.temporal.activities import execute_calculation
    from gibbs.temporal.workflows import RunCalculationWorkflow

    env = await WorkflowEnvironment.start_local()
    try:
        settings = Settings(executor="temporal", temporal_task_queue="test-queue")
        executor = TemporalJobExecutor(settings)
        executor._client = env.client  # bypass connect: use the test server

        async with Worker(
            env.client,
            task_queue="test-queue",
            workflows=[RunCalculationWorkflow],
            activities=[execute_calculation],
            # See test_campaign_loop_runs_on_the_worker: beartype's import hook
            # breaks Temporal's workflow sandbox under pytest, so validation
            # fails here for reasons unrelated to the workflow.
            workflow_runner=UnsandboxedWorkflowRunner(),
        ):
            monkeypatch.setattr(runner_registry, "_executor", executor)
            r = await client.post(
                "/campaigns",
                json={
                    "name": "temporal ising",
                    "strategy": "grid",
                    "simulation_budget": 4,
                    "lattice_size": 8,
                },
            )
            campaign_id = r.json()["id"]
            r = await client.post(f"/campaigns/{campaign_id}/start")
            assert r.status_code == 200
            await asyncio.wait_for(runner_registry.wait(campaign_id), timeout=180)

            campaign = (await client.get(f"/campaigns/{campaign_id}")).json()
            assert campaign["status"] == "COMPLETED"
            assert campaign["simulations_used"] == 4

            calcs = (await client.get(f"/campaigns/{campaign_id}/calculations")).json()
            assert all(c["status"] == "SUCCEEDED" for c in calcs)
            # Every calculation ran as a durable workflow on the test server.
            workflows = [w async for w in env.client.list_workflows()]
            workflow_ids = {w.id for w in workflows}
            assert {f"calc-{c['id']}" for c in calcs} <= workflow_ids

            events = (await client.get(f"/campaigns/{campaign_id}/agent-events")).json()
            types = {e["event_type"] for e in events}
            assert {"JOB_STARTED", "JOB_SUCCEEDED", "CAMPAIGN_COMPLETED"} <= types
    finally:
        monkeypatch.setattr(runner_registry, "_executor", None)
        await env.shutdown()


@pytest.mark.skipif(
    not os.environ.get("ALLOYLAB_TEMPORAL_TEST"),
    reason="set ALLOYLAB_TEMPORAL_TEST=1 to run the full Temporal round trip "
    "(downloads a local test server on first use)",
)
async def test_campaign_loop_runs_on_the_worker(client, monkeypatch):
    """The campaign loop itself is a workflow activity, so it outlives the API
    process that started it. Previously the loop was a bare asyncio task inside
    the API: a container recycle cancelled it mid-iteration and the campaign sat
    at RUNNING forever with no event recorded."""
    import asyncio

    from temporalio.testing import WorkflowEnvironment
    from temporalio.worker import UnsandboxedWorkflowRunner, Worker

    from gibbs.agent.loop import runner_registry
    from gibbs.config import get_settings
    from gibbs.temporal.activities import run_campaign
    from gibbs.temporal.campaign import campaign_workflow_id
    from gibbs.temporal.workflows import RunCampaignWorkflow

    env = await WorkflowEnvironment.start_local()
    try:
        monkeypatch.setenv("ALLOYLAB_EXECUTOR", "temporal")
        monkeypatch.setenv("ALLOYLAB_TEMPORAL_TASK_QUEUE", "test-campaign-queue")
        get_settings.cache_clear()
        # Bypass connect: talk to the in-test server instead of a real cluster.
        monkeypatch.setattr(
            "gibbs.temporal.campaign.connect_temporal_client",
            lambda settings: _resolved(env.client),
        )

        async with Worker(
            env.client,
            task_queue="test-campaign-queue",
            workflows=[RunCampaignWorkflow],
            activities=[run_campaign],
            # Unsandboxed under pytest only: beartype's import hook cannot be
            # re-imported inside Temporal's workflow sandbox, so validation
            # fails here for reasons unrelated to the workflow itself. The
            # deployed worker (gibbs.worker) still runs sandboxed.
            workflow_runner=UnsandboxedWorkflowRunner(),
        ):
            r = await client.post(
                "/campaigns",
                json={
                    "name": "worker-hosted ising",
                    "strategy": "grid",
                    "simulation_budget": 4,
                    "lattice_size": 8,
                },
            )
            campaign_id = r.json()["id"]
            r = await client.post(f"/campaigns/{campaign_id}/start")
            assert r.status_code == 200, r.text

            # Nothing is running in this process: the loop lives on the worker.
            assert not runner_registry.is_running(campaign_id)

            handle = env.client.get_workflow_handle(campaign_workflow_id(campaign_id))
            await asyncio.wait_for(handle.result(), timeout=180)

            campaign = (await client.get(f"/campaigns/{campaign_id}")).json()
            assert campaign["status"] == "COMPLETED"
            assert campaign["simulations_used"] == 4

            events = (await client.get(f"/campaigns/{campaign_id}/agent-events")).json()
            types = {e["event_type"] for e in events}
            assert {"CAMPAIGN_STARTED", "JOB_SUCCEEDED", "CAMPAIGN_COMPLETED"} <= types
    finally:
        get_settings.cache_clear()
        await env.shutdown()


async def _resolved(value):
    return value
