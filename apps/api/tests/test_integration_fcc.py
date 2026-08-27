"""Milestone 4 integration: an icet-backed FCC Ni-Al campaign end-to-end —
symmetry enumeration, cluster-vector CE fits with LOOCV, hull discovery,
3D structure payloads, and the fcc benchmark endpoint."""

import asyncio

from gibbs.agent.loop import runner_registry


async def _run_to_completion(client, campaign_id: str, timeout_s: float = 180.0) -> dict:
    r = await client.post(f"/campaigns/{campaign_id}/start")
    assert r.status_code == 200, r.text
    await asyncio.wait_for(runner_registry.wait(campaign_id), timeout=timeout_s)
    r = await client.get(f"/campaigns/{campaign_id}")
    return r.json()


async def test_full_fcc_campaign(client):
    r = await client.post(
        "/campaigns",
        json={
            "name": "fcc integration",
            "problem_type": "fcc_v2",
            "strategy": "uncertainty",
            "simulation_budget": 12,
        },
    )
    assert r.status_code == 201, r.text
    campaign = r.json()
    assert campaign["problem_type"] == "fcc_v2"
    assert "problem_config" not in campaign  # hidden ECIs must not leak
    campaign_id = campaign["id"]

    campaign = await _run_to_completion(client, campaign_id)
    assert campaign["status"] == "COMPLETED"
    assert campaign["simulations_used"] == 12

    structures = (await client.get(f"/campaigns/{campaign_id}/structures")).json()
    assert len(structures) >= 20
    s = next(s for s in structures if s["n_sites"] > 1)
    # Real 3D crystal payloads from icet/ASE.
    assert len(s["lattice"]) == 3 and len(s["lattice"][0]) == 3
    assert len(s["positions"]) == s["n_sites"]
    assert set(s["atomic_numbers"]) <= {13, 28}
    assert "Ni" in s["chemical_formula"] or "Al" in s["chemical_formula"]
    # Cluster vector stored as the design row (zerolet first).
    assert any(abs(st["composition"] - 0.25) < 1e-9 for st in structures)

    calcs = (await client.get(f"/campaigns/{campaign_id}/calculations")).json()
    assert len(calcs) == 12
    assert all(c["calculation_type"] == "STRUCTURE_ENERGY" for c in calcs)
    assert all(c["status"] == "SUCCEEDED" for c in calcs)
    first_two_x = {c["input_parameters"]["composition"] for c in calcs[:2]}
    assert first_two_x == {0.0, 1.0}

    models = (await client.get(f"/campaigns/{campaign_id}/models")).json()
    assert models and models[-1]["type"] == "cluster_expansion"
    coefs = models[-1]["validation_metrics"]["coefficients"]
    # Full cluster-space coefficient vector reported (k > 4).
    assert len(coefs) >= 5

    hull = (await client.get(f"/campaigns/{campaign_id}/hull")).json()
    assert hull["endpoints_measured"] is True
    assert len(hull["stable_labels"]) >= 3  # ordering compounds discovered
    assert min(p["e_form"] for p in hull["points"] if p["e_form"] is not None) < -0.01

    events = (await client.get(f"/campaigns/{campaign_id}/agent-events")).json()
    pool_events = [e for e in events if e["event_type"] == "POOL_ENUMERATED"]
    assert pool_events and "icet" in pool_events[0]["action"]


async def test_fcc_benchmark_endpoint(client):
    r = await client.post(
        "/benchmarks",
        json={
            "problem": "fcc",
            "strategies": ["random", "uncertainty"],
            "budget": 10,
            "seeds": [1, 2],
        },
    )
    assert r.status_code == 201, r.text
    bid = r.json()["id"]
    for _ in range(240):
        b = (await client.get(f"/benchmarks/{bid}")).json()
        if b["status"] != "RUNNING":
            break
        await asyncio.sleep(0.5)
    assert b["status"] == "COMPLETED", b.get("error")
    assert b["summary"]["problem"] == "fcc"
    per = b["summary"]["per_strategy"]
    assert set(per) == {"random", "uncertainty"}
    for stats in per.values():
        assert stats["mean_hull_rmse"] >= 0
