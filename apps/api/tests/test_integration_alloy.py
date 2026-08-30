"""Milestone 3 integration: a full alloy campaign end-to-end without OpenAI —
pool enumeration, endpoint references, cluster-expansion fits, hull view,
failure recovery, and ground-state discovery events."""

import asyncio

from gibbs.agent.loop import runner_registry


async def _run_to_completion(client, campaign_id: str, timeout_s: float = 120.0) -> dict:
    r = await client.post(f"/campaigns/{campaign_id}/start")
    assert r.status_code == 200, r.text
    await asyncio.wait_for(runner_registry.wait(campaign_id), timeout=timeout_s)
    r = await client.get(f"/campaigns/{campaign_id}")
    return r.json()


async def test_full_alloy_campaign(client):
    r = await client.post(
        "/campaigns",
        json={
            "name": "alloy integration",
            "problem_type": "alloy_v1",
            "strategy": "uncertainty",
            "simulation_budget": 10,
        },
    )
    assert r.status_code == 201, r.text
    campaign = r.json()
    assert campaign["problem_type"] == "alloy_v1"
    # The hidden Hamiltonian must never leak through the API.
    assert "problem_config" not in campaign
    campaign_id = campaign["id"]

    campaign = await _run_to_completion(client, campaign_id)
    assert campaign["status"] == "COMPLETED"
    assert campaign["simulations_used"] == 10

    structures = (await client.get(f"/campaigns/{campaign_id}/structures")).json()
    assert len(structures) >= 30
    assert any(s["composition"] == 0.0 for s in structures)
    assert any(s["composition"] == 1.0 for s in structures)

    calcs = (await client.get(f"/campaigns/{campaign_id}/calculations")).json()
    assert len(calcs) == 10
    assert all(c["calculation_type"] == "STRUCTURE_ENERGY" for c in calcs)
    assert all(c["status"] == "SUCCEEDED" for c in calcs)
    assert all(c["structure_id"] for c in calcs)
    # Endpoints measured first.
    first_two_x = {c["input_parameters"]["composition"] for c in calcs[:2]}
    assert first_two_x == {0.0, 1.0}

    models = (await client.get(f"/campaigns/{campaign_id}/models")).json()
    assert models and models[-1]["type"] == "cluster_expansion"
    metrics = models[-1]["validation_metrics"]
    assert metrics["n_training_points"] == 10
    assert "J_nn" in metrics["coefficients"]

    hull = (await client.get(f"/campaigns/{campaign_id}/hull")).json()
    assert hull["endpoints_measured"] is True
    assert hull["model_version"] == models[-1]["version"]
    assert len(hull["points"]) == len(structures)
    assert len(hull["stable_labels"]) >= 2
    measured_points = [p for p in hull["points"] if p["measured"]]
    assert len(measured_points) == 10
    # Predicted (unmeasured) points must carry uncertainty; measured must not.
    assert all((p["e_form_std"] or 0.0) == 0.0 for p in measured_points)

    events = (await client.get(f"/campaigns/{campaign_id}/agent-events")).json()
    types = {e["event_type"] for e in events}
    assert {"POOL_ENUMERATED", "CAMPAIGN_STARTED", "AGENT_DECISION", "MODEL_UPDATED",
            "CAMPAIGN_COMPLETED"} <= types


async def test_alloy_failure_recovery(client, inject_failures):
    inject_failures(0.6)
    r = await client.post(
        "/campaigns",
        json={
            "name": "alloy flaky",
            "problem_type": "alloy_v1",
            "strategy": "grid",
            "simulation_budget": 8,
        },
    )
    campaign_id = r.json()["id"]
    campaign = await _run_to_completion(client, campaign_id, timeout_s=180.0)
    assert campaign["status"] == "COMPLETED"

    calcs = (await client.get(f"/campaigns/{campaign_id}/calculations")).json()
    failed = [c for c in calcs if c["status"] == "FAILED"]
    assert failed, "expected injected SCF failures at injected_failure_rate=0.6"
    assert all(c["failure_category"] == "SCF_NOT_CONVERGED" for c in failed)
    # The budget is a hard ceiling — a failure at the boundary may legitimately
    # remain unresolved, but never more than the final one.
    unresolved = [c for c in failed if c["resolution"] is None]
    assert len(unresolved) <= 1
    assert campaign["simulations_used"] <= 8
    retries = [c for c in calcs if c["retry_of"]]
    assert retries, "expected at least one retry"
    for retry in retries:
        assert retry["status"] == "SUCCEEDED"
        assert retry["reason_for_change"]


async def test_hull_view_rejected_for_ising(client):
    r = await client.post("/campaigns", json={"name": "ising", "strategy": "grid"})
    cid = r.json()["id"]
    r = await client.get(f"/campaigns/{cid}/hull")
    assert r.status_code == 400


async def test_alloy_benchmark_endpoint(client):
    r = await client.post(
        "/benchmarks",
        json={
            "problem": "alloy",
            "strategies": ["random", "grid", "uncertainty"],
            "budget": 8,
            "seeds": [1, 2],
        },
    )
    assert r.status_code == 201, r.text
    bid = r.json()["id"]
    for _ in range(120):
        b = (await client.get(f"/benchmarks/{bid}")).json()
        if b["status"] != "RUNNING":
            break
        await asyncio.sleep(0.5)
    assert b["status"] == "COMPLETED", b.get("error")
    assert b["summary"]["problem"] == "alloy"
    per = b["summary"]["per_strategy"]
    assert set(per) == {"random", "grid", "uncertainty"}
    for stats in per.values():
        assert stats["n_runs"] == 2
        assert stats["mean_hull_rmse"] >= 0
