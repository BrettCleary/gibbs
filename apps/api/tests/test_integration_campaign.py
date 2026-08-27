"""Integration test (plan section 34): a full synthetic campaign completes
without OpenAI or Quantum ESPRESSO — deterministic heuristic decisions, real
Monte Carlo, surrogate fits, agent events, and provenance."""

import asyncio

from gibbs.agent.loop import runner_registry


async def _run_to_completion(client, campaign_id: str, timeout_s: float = 120.0) -> dict:
    r = await client.post(f"/campaigns/{campaign_id}/start")
    assert r.status_code == 200, r.text
    # The loop runs on this event loop; wait for its task directly.
    await asyncio.wait_for(runner_registry.wait(campaign_id), timeout=timeout_s)
    r = await client.get(f"/campaigns/{campaign_id}")
    return r.json()


async def test_full_synthetic_campaign(client):
    r = await client.post(
        "/campaigns",
        json={
            "name": "ising integration",
            "strategy": "uncertainty",
            "simulation_budget": 5,
            "lattice_size": 8,
            "temperature_min": 1.5,
            "temperature_max": 3.5,
        },
    )
    campaign_id = r.json()["id"]
    campaign = await _run_to_completion(client, campaign_id)

    assert campaign["status"] == "COMPLETED"
    assert campaign["simulations_used"] == 5
    assert campaign["stopping_rationale"]

    calcs = (await client.get(f"/campaigns/{campaign_id}/calculations")).json()
    assert len(calcs) == 5
    assert all(c["status"] == "SUCCEEDED" for c in calcs)
    assert all(c["provenance"] for c in calcs)
    assert all(c["output"]["susceptibility"] >= 0 for c in calcs)

    models = (await client.get(f"/campaigns/{campaign_id}/models")).json()
    assert len(models) >= 1
    final = models[-1]
    assert final["validation_metrics"]["tc_mean"] is not None
    assert len(final["training_calculation_ids"]) == 5

    events = (await client.get(f"/campaigns/{campaign_id}/agent-events")).json()
    types = {e["event_type"] for e in events}
    assert {"CAMPAIGN_STARTED", "AGENT_DECISION", "JOB_STARTED", "JOB_SUCCEEDED",
            "MODEL_UPDATED", "CAMPAIGN_COMPLETED"} <= types
    decisions = [e for e in events if e["event_type"] == "AGENT_DECISION"]
    assert all(e["hypothesis"] for e in decisions)

    view = (await client.get(f"/campaigns/{campaign_id}/surrogate")).json()
    assert view["tc_mean"] is not None
    assert 1.5 <= view["tc_mean"] <= 3.5
    assert len(view["measured_temperatures"]) == 5


async def test_failure_recovery_campaign(client):
    r = await client.post(
        "/campaigns",
        json={
            "name": "flaky",
            "strategy": "grid",
            "simulation_budget": 6,
            "lattice_size": 8,
            "failure_rate": 0.9,
        },
    )
    campaign_id = r.json()["id"]
    campaign = await _run_to_completion(client, campaign_id, timeout_s=180.0)
    assert campaign["status"] == "COMPLETED"

    calcs = (await client.get(f"/campaigns/{campaign_id}/calculations")).json()
    failed = [c for c in calcs if c["status"] == "FAILED"]
    retries = [c for c in calcs if c["retry_of"]]
    assert failed, "expected injected failures at failure_rate=0.9"
    # The budget is a hard ceiling — a failure at the boundary may legitimately
    # remain unresolved, but never more than the final one; every other failure
    # is explicitly resolved and every retry preserves lineage.
    unresolved = [c for c in failed if c["resolution"] is None]
    assert len(unresolved) <= 1
    assert campaign["simulations_used"] <= 6
    for retry in retries:
        assert retry["changed_parameters"]
        assert retry["reason_for_change"]
        assert retry["status"] == "SUCCEEDED"

    events = (await client.get(f"/campaigns/{campaign_id}/agent-events")).json()
    assert any(e["event_type"] == "JOB_FAILED" for e in events)
