"""Milestone 8 integration: property-search campaign end-to-end — energy +
bulk-modulus queries, dual surrogates, finite-T verification MC on the fitted
CE, ranked candidates, and a final recommendation."""

import asyncio

from alloylab.agent.loop import runner_registry


async def _run_to_completion(client, campaign_id: str, timeout_s: float = 300.0) -> dict:
    r = await client.post(f"/campaigns/{campaign_id}/start")
    assert r.status_code == 200, r.text
    await asyncio.wait_for(runner_registry.wait(campaign_id), timeout=timeout_s)
    return (await client.get(f"/campaigns/{campaign_id}")).json()


async def test_full_property_campaign(client):
    r = await client.post(
        "/campaigns",
        json={
            "name": "stiff & stable",
            "problem_type": "property_v3",
            "strategy": "uncertainty",
            "simulation_budget": 14,
            "temperature_threshold": 600.0,
        },
    )
    assert r.status_code == 201, r.text
    campaign_id = r.json()["id"]
    assert "problem_config" not in r.json()

    campaign = await _run_to_completion(client, campaign_id)
    assert campaign["status"] == "COMPLETED"
    assert campaign["simulations_used"] == 14

    calcs = (await client.get(f"/campaigns/{campaign_id}/calculations")).json()
    energy_calcs = [c for c in calcs if c["calculation_type"] == "STRUCTURE_ENERGY"]
    mc_calcs = [c for c in calcs if c["calculation_type"] == "MONTE_CARLO"]
    assert all(c["status"] == "SUCCEEDED" for c in calcs)
    assert all("bulk_modulus_gpa" in c["output"] for c in energy_calcs)
    # The tail of the budget went to finite-T verification on the fitted CE.
    assert mc_calcs, "expected at least one verification MC run"
    assert all("ecis" in c["input_parameters"] for c in mc_calcs)
    assert all(c["input_parameters"]["temperature"] == 600.0 for c in mc_calcs)
    assert all("sro" in c["output"] for c in mc_calcs)

    cands = (await client.get(f"/campaigns/{campaign_id}/candidates")).json()
    assert cands["temperature_threshold"] == 600.0
    assert cands["candidates"], "candidate table populated"
    verdicts = {c["stability_at_threshold"] for c in cands["candidates"]}
    assert verdicts & {"ordered", "disordered"}, "some candidate was verified"
    top = cands["top_candidate_label"]
    if top is not None:
        c = next(c for c in cands["candidates"] if c["label"] == top)
        assert c["measured"] and c["stable_0k"] and 0.0 < c["x"] < 1.0
        assert c["stability_at_threshold"] != "disordered"

    events = (await client.get(f"/campaigns/{campaign_id}/agent-events")).json()
    types = {e["event_type"] for e in events}
    assert "FINAL_RECOMMENDATION" in types
    rec = next(e for e in events if e["event_type"] == "FINAL_RECOMMENDATION")
    assert "GPa" in rec["action"] or "No stable" in rec["action"]

    hull = (await client.get(f"/campaigns/{campaign_id}/hull")).json()
    assert hull["endpoints_measured"]


async def test_property_benchmark_endpoint(client):
    r = await client.post(
        "/benchmarks",
        json={"problem": "property", "strategies": ["random", "uncertainty"], "budget": 10, "seeds": [1, 2]},
    )
    assert r.status_code == 201, r.text
    bid = r.json()["id"]
    for _ in range(240):
        b = (await client.get(f"/benchmarks/{bid}")).json()
        if b["status"] != "RUNNING":
            break
        await asyncio.sleep(0.5)
    assert b["status"] == "COMPLETED", b.get("error")
    per = b["summary"]["per_strategy"]
    assert set(per) == {"random", "uncertainty"}
    for stats in per.values():
        assert stats["mean_regret_gpa"] >= 0
        assert 0.0 <= stats["frac_truly_stable"] <= 1.0
