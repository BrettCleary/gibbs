"""Milestone 8 integration: property-search campaign end-to-end — energy +
bulk-modulus queries, dual surrogates, finite-T verification MC on the fitted
CE, ranked candidates, and a final recommendation."""

import asyncio

from gibbs.agent.loop import runner_registry


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


async def test_report_generated_and_served(client):
    r = await client.post(
        "/campaigns",
        json={"name": "report", "problem_type": "property_v3", "strategy": "grid",
              "simulation_budget": 10, "temperature_threshold": 200.0},
    )
    campaign_id = r.json()["id"]
    campaign = await _run_to_completion(client, campaign_id)
    assert campaign["status"] == "COMPLETED"

    report = (await client.get(f"/campaigns/{campaign_id}/report")).json()
    assert report["problem_type"] == "property_v3"
    assert report["budget"]["used"] == 10
    assert report["engines"]
    assert report["key_results"], "key results extracted"
    assert report["decision_trail"], "decision trail preserved"
    assert report["limitations"], "limitations stated"
    assert "hidden" in " ".join(report["limitations"]).lower() or "synthetic" in " ".join(report["limitations"]).lower()
    assert report["narrative"] and "Objective" in report["narrative"]
    assert report["model"]["loocv_rmse"] is not None

    events = (await client.get(f"/campaigns/{campaign_id}/agent-events")).json()
    assert any(e["event_type"] == "REPORT_GENERATED" for e in events)
    # Report is persisted on the campaign (served without recomputation).
    again = (await client.get(f"/campaigns/{campaign_id}/report")).json()
    assert again["generated_at"] == report["generated_at"]


async def test_report_on_the_fly_for_unfinished_campaign(client):
    r = await client.post("/campaigns", json={"name": "fresh", "strategy": "grid"})
    cid = r.json()["id"]
    report = (await client.get(f"/campaigns/{cid}/report")).json()
    assert report["status"] == "CREATED"
    assert any("provisional" in l for l in report["limitations"])
