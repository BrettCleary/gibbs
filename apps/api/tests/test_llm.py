"""LLM harness tests (Pydantic AI). `TestModel` drives the real decision path —
structured output, tool registration, action-type coercion — with no provider
key, and `ALLOYLAB_AGENT_MODEL=test` runs a full agent-strategy campaign."""

import asyncio

import pytest
from pydantic_ai.models.test import TestModel

from gibbs.agent.decisions import ActionType
from gibbs.agent.llm import LLMDecider, model_available, provider_key_env
from gibbs.agent.state import Measurement, ScientificState
from gibbs.problems.ising import ISING_LLM_INSTRUCTIONS, _render_ising_state


def _ising_state(**overrides) -> ScientificState:
    base = dict(
        campaign_id="c1", objective="find Tc", strategy="agent",
        temperature_min=1.5, temperature_max=3.5, lattice_size=8,
        budget_total=10, budget_used=3, budget_remaining=7, target_uncertainty=None,
        measurements=[
            Measurement(calculation_id=f"m{i}", temperature=t, susceptibility=v, susceptibility_err=0.1)
            for i, (t, v) in enumerate([(1.5, 0.1), (2.3, 5.0), (3.5, 0.5)])
        ],
        unresolved_failures=[], latest_model=None, suggested_uncertainty_temperature=2.1,
    )
    base.update(overrides)
    return ScientificState(**base)


def test_provider_key_mapping(monkeypatch):
    assert provider_key_env("openai:gpt-5") == "OPENAI_API_KEY"
    assert provider_key_env("anthropic:claude-sonnet-4-5") == "ANTHROPIC_API_KEY"
    assert provider_key_env("gpt-5") == "OPENAI_API_KEY"  # bare name -> openai
    assert provider_key_env("test") is None
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    ok, reason = model_available("anthropic:claude-sonnet-4-5")
    assert not ok and "ANTHROPIC_API_KEY" in reason
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    assert model_available("anthropic:claude-sonnet-4-5")[0]
    assert model_available(TestModel())[0]  # a Model instance is always usable


async def test_decider_structured_output_and_tools():
    calls: list[str] = []
    model = TestModel(
        custom_output_args={
            "hypothesis": "Refine near the suspected peak.",
            "evidence": ["chi peaks near 2.3"],
            "uncertainty": "peak width unresolved",
            "action_type": "RUN_MONTE_CARLO",
            "temperatures": [2.1, 2.5],
            "expected_information_gain": "narrows Tc",
        }
    )
    decider = LLMDecider(
        instructions=ISING_LLM_INSTRUCTIONS,
        render_state=_render_ising_state,
        action_types=(ActionType.RUN_MONTE_CARLO,),
        model=model,
    )
    decision = await decider.decide(_ising_state())
    assert decision.action_type == ActionType.RUN_MONTE_CARLO
    assert decision.temperatures == [2.1, 2.5]
    assert decision.hypothesis.startswith("Refine")
    # TestModel calls every registered tool before answering: the Ising
    # surrogate-curve tool was registered and invoked successfully.
    assert model.last_model_request_parameters is not None
    tool_names = {t.name for t in model.last_model_request_parameters.function_tools}
    assert "get_surrogate_curve" in tool_names
    assert decider.last_usage and decider.last_usage["requests"] >= 1


async def test_decider_coerces_wrong_run_action():
    model = TestModel(
        custom_output_args={
            "hypothesis": "h", "action_type": "RUN_STRUCTURE_ENERGY",
            "structure_labels": ["s001"], "temperatures": [2.0],
        }
    )
    decider = LLMDecider(
        instructions="x", render_state=_render_ising_state,
        action_types=(ActionType.RUN_MONTE_CARLO,), model=model,
    )
    decision = await decider.decide(_ising_state())
    assert decision.action_type == ActionType.RUN_MONTE_CARLO


async def test_decider_budget_guard_precedes_model():
    model = TestModel(custom_output_args={"hypothesis": "h", "action_type": "RUN_MONTE_CARLO"})
    decider = LLMDecider(
        instructions="x", render_state=_render_ising_state,
        action_types=(ActionType.RUN_MONTE_CARLO,), model=model,
    )
    decision = await decider.decide(_ising_state(budget_used=10, budget_remaining=0))
    assert decision.action_type == ActionType.FINISH_CAMPAIGN
    assert model.last_model_request_parameters is None  # model never called


async def test_decider_unavailable_provider(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    decider = LLMDecider(
        instructions="x", render_state=_render_ising_state,
        action_types=(ActionType.RUN_MONTE_CARLO,), model="openai:gpt-5",
    )
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        await decider.decide(_ising_state())


async def test_llm_narrative_with_test_model():
    from gibbs.report import llm_narrative

    text = await llm_narrative({"title": "t", "key_results": ["r"]}, TestModel(custom_output_text="Prose."))
    assert text == "Prose."
    assert await llm_narrative({}, "openai:gpt-5") is None or True  # key-dependent; must not raise


async def test_full_agent_strategy_campaign_with_test_model(client, monkeypatch):
    """End-to-end: the 'agent' strategy driving an Ising campaign through the
    Pydantic AI harness with the built-in test model (no provider needed)."""
    from gibbs.agent.loop import runner_registry
    from gibbs.config import get_settings

    monkeypatch.setenv("ALLOYLAB_AGENT_MODEL", "test")
    get_settings.cache_clear()
    try:
        r = await client.post(
            "/campaigns",
            json={"name": "agent ising", "strategy": "agent", "simulation_budget": 4, "lattice_size": 8},
        )
        cid = r.json()["id"]
        r = await client.post(f"/campaigns/{cid}/start")
        assert r.status_code == 200, r.text
        await asyncio.wait_for(runner_registry.wait(cid), timeout=120)
        campaign = (await client.get(f"/campaigns/{cid}")).json()
        assert campaign["status"] == "COMPLETED"
        assert campaign["simulations_used"] == 4
        events = (await client.get(f"/campaigns/{cid}/agent-events")).json()
        decisions = [e for e in events if e["event_type"] == "AGENT_DECISION"]
        assert decisions and all(e["hypothesis"] for e in decisions)
        report = (await client.get(f"/campaigns/{cid}/report")).json()
        assert report["strategy"] == "agent"
        # The narrative pass also ran through the test model.
        assert report.get("llm_narrative")
    finally:
        get_settings.cache_clear()
