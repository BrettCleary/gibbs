"""Milestone 6 integration: a real-calculator campaign end-to-end with the EMT
engine — actual physics, no hidden Hamiltonian — plus espresso-engine
validation. Real pw.x runs are exercised in the science suite (env-gated)."""

import asyncio

from gibbs.agent.loop import runner_registry


async def _run_to_completion(client, campaign_id: str, timeout_s: float = 240.0) -> dict:
    r = await client.post(f"/campaigns/{campaign_id}/start")
    assert r.status_code == 200, r.text
    await asyncio.wait_for(runner_registry.wait(campaign_id), timeout=timeout_s)
    r = await client.get(f"/campaigns/{campaign_id}")
    return r.json()


async def test_full_emt_dft_campaign(client):
    r = await client.post(
        "/campaigns",
        json={
            "name": "EMT real-calculator campaign",
            "problem_type": "dft_v3",
            "dft_engine": "emt",
            "strategy": "uncertainty",
            "simulation_budget": 10,
        },
    )
    assert r.status_code == 201, r.text
    campaign_id = r.json()["id"]

    campaign = await _run_to_completion(client, campaign_id)
    assert campaign["status"] == "COMPLETED"
    assert campaign["simulations_used"] == 10

    calcs = (await client.get(f"/campaigns/{campaign_id}/calculations")).json()
    assert len(calcs) == 10
    assert all(c["engine"] == "ase.calculators.emt.EMT" for c in calcs)
    assert all(c["status"] == "SUCCEEDED" for c in calcs)
    out = calcs[0]["output"]
    # Real relaxed energies with per-structure equilibrium data.
    assert "optimal_lattice_constant" in out
    assert "bulk_modulus_gpa" in out
    assert 3.2 < out["optimal_lattice_constant"] < 4.4

    events = (await client.get(f"/campaigns/{campaign_id}/agent-events")).json()
    assert any(
        e["event_type"] == "ENGINE_SELECTED" and "EMT" in e["action"] for e in events
    )

    hull = (await client.get(f"/campaigns/{campaign_id}/hull")).json()
    assert hull["endpoints_measured"] is True
    # EMT is an honest (if crude) model: whatever the hull, it must exist and
    # include the pure endpoints.
    assert len(hull["stable_labels"]) >= 2

    models = (await client.get(f"/campaigns/{campaign_id}/models")).json()
    assert models and models[-1]["type"] == "cluster_expansion"


async def test_espresso_engine_validated_at_create(client, monkeypatch):
    from gibbs.config import get_settings

    monkeypatch.setenv("ALLOYLAB_PW_COMMAND", "/nonexistent/pw.x")
    get_settings.cache_clear()
    r = await client.post(
        "/campaigns",
        json={"name": "qe", "problem_type": "dft_v3", "dft_engine": "espresso"},
    )
    get_settings.cache_clear()
    assert r.status_code == 400
    assert "unavailable" in r.json()["detail"]


async def test_calculation_log_endpoint_missing(client):
    r = await client.post("/campaigns", json={"name": "x", "strategy": "grid"})
    assert r.status_code == 201
    r = await client.get("/calculations/doesnotexist/log")
    assert r.status_code == 404
