"""Milestone 5 integration: a phase-diagram campaign end-to-end — canonical MC
jobs at (x, T), per-slice boundary fits with uncertainty, the T-x view, and
the phase benchmark endpoint."""

import asyncio

import pytest

from gibbs.agent.decisions import ActionType, ScientificDecision
from gibbs.agent.loop import runner_registry
from gibbs.problems.phase import PhaseProblem, PhaseSlice, PhaseState


def _state(**overrides) -> PhaseState:
    base = dict(
        campaign_id="c1",
        objective="map Tc(x)",
        strategy="uncertainty",
        budget_total=12,
        budget_used=0,
        budget_remaining=12,
        target_uncertainty=None,
        unresolved_failures=[],
        latest_model=None,
        temperature_min=300.0,
        temperature_max=2400.0,
        slices=[PhaseSlice(x=0.25), PhaseSlice(x=0.5)],
        suggested_slice_x=0.5,
        suggested_temperature=1000.0,
    )
    base.update(overrides)
    return PhaseState(**base)


def test_validate_snaps_composition_to_slice():
    problem = PhaseProblem()
    d = ScientificDecision(
        hypothesis="h",
        action_type=ActionType.RUN_MONTE_CARLO,
        composition=0.27,
        temperatures=[100.0, 9000.0],
    )
    cleaned = problem.validate(_state(), d)
    assert cleaned.composition == 0.25
    assert cleaned.temperatures == [300.0, 2400.0]


def test_validate_defaults_missing_composition_and_temperature():
    problem = PhaseProblem()
    d = ScientificDecision(hypothesis="h", action_type=ActionType.RUN_MONTE_CARLO)
    cleaned = problem.validate(_state(), d)
    assert cleaned.composition == 0.5  # suggested slice
    assert cleaned.temperatures == [1000.0]  # suggested temperature


async def _run_to_completion(client, campaign_id: str, timeout_s: float = 240.0) -> dict:
    r = await client.post(f"/campaigns/{campaign_id}/start")
    assert r.status_code == 200, r.text
    await asyncio.wait_for(runner_registry.wait(campaign_id), timeout=timeout_s)
    r = await client.get(f"/campaigns/{campaign_id}")
    return r.json()


async def test_full_phase_campaign(client):
    r = await client.post(
        "/campaigns",
        json={
            "name": "phase integration",
            "problem_type": "phase_v2",
            "strategy": "uncertainty",
            "simulation_budget": 9,
            "composition_slices": [0.5],
        },
    )
    assert r.status_code == 201, r.text
    campaign = r.json()
    assert campaign["problem_type"] == "phase_v2"
    assert campaign["temperature_min"] == 100.0  # Kelvin defaults applied
    assert campaign["temperature_max"] == 1200.0
    campaign_id = campaign["id"]

    campaign = await _run_to_completion(client, campaign_id)
    assert campaign["status"] == "COMPLETED"
    assert campaign["simulations_used"] == 9

    calcs = (await client.get(f"/campaigns/{campaign_id}/calculations")).json()
    assert len(calcs) == 9
    assert all(c["calculation_type"] == "MONTE_CARLO" for c in calcs)
    assert all(c["engine"] == "mchammer.CanonicalEnsemble" for c in calcs)
    assert all(c["status"] == "SUCCEEDED" for c in calcs)
    assert all(c["input_parameters"]["composition"] == 0.5 for c in calcs)
    out = calcs[0]["output"]
    assert "heat_capacity" in out and "sro" in out
    assert calcs[0]["provenance"]["heat_capacity_units"] == "k_B per atom"

    models = (await client.get(f"/campaigns/{campaign_id}/models")).json()
    assert models and models[-1]["type"] == "phase_boundary"
    assert models[-1]["validation_metrics"]["max_tc_std"] is not None

    diagram = (await client.get(f"/campaigns/{campaign_id}/phase-diagram")).json()
    assert diagram["temperature_min"] == 100.0
    assert len(diagram["slices"]) == 1
    s = diagram["slices"][0]
    assert s["x"] == 0.5
    assert s["tc_mean"] is not None
    assert 100.0 <= s["tc_mean"] <= 1200.0
    assert s["tc_std"] is not None and s["tc_std"] >= 0
    assert len(s["curve_t"]) == 61
    assert len(s["measured"]) == 9

    events = (await client.get(f"/campaigns/{campaign_id}/agent-events")).json()
    assert any(
        e["event_type"] == "MODEL_UPDATED" and "Phase boundary" in e["action"]
        for e in events
    )


async def test_phase_diagram_rejected_for_other_problems(client):
    r = await client.post("/campaigns", json={"name": "ising", "strategy": "grid"})
    cid = r.json()["id"]
    assert (await client.get(f"/campaigns/{cid}/phase-diagram")).status_code == 400


async def test_phase_benchmark_endpoint(client):
    r = await client.post(
        "/benchmarks",
        json={
            "problem": "phase",
            "strategies": ["grid"],
            "budget": 6,
            "seeds": [11],
        },
    )
    assert r.status_code == 201, r.text
    bid = r.json()["id"]
    for _ in range(600):
        b = (await client.get(f"/benchmarks/{bid}")).json()
        if b["status"] != "RUNNING":
            break
        await asyncio.sleep(0.5)
    assert b["status"] == "COMPLETED", b.get("error")
    assert b["summary"]["problem"] == "phase"
    stats = b["summary"]["per_strategy"]["grid"]
    assert stats["mean_boundary_error"] >= 0
    assert stats["n_runs"] == 1
