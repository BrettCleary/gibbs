"""LLM scientist decider built on Pydantic AI.

Problem-agnostic: each problem adapter supplies its instructions, a state
renderer, and the run-action it accepts. The LLM chooses experiments and
interprets results; it never computes numbers. All quantities it sees come
from the deterministic state/tools, and its output is forced into a structured
decision schema (Pydantic AI `output_type`) that the problem adapter validates.

Models are Pydantic AI model strings (provider-prefixed), e.g. `openai:gpt-5`,
`anthropic:claude-sonnet-4-5`, `google-gla:gemini-2.5-pro`; the provider's API
key must be present in the environment. A `Model` instance (e.g. Pydantic AI's
`TestModel`) may be passed directly, which is how the decision path is
unit-tested without any provider.
"""

from __future__ import annotations

import json
import os
from typing import Callable, Sequence

from pydantic import BaseModel, Field

from .decisions import ActionType, ScientificDecision
from .state import BaseScientificState
from .strategies import check_stopping

# Provider prefix -> environment variable holding its API key.
PROVIDER_KEY_ENV = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google-gla": "GEMINI_API_KEY",
    "google-vertex": "GOOGLE_APPLICATION_CREDENTIALS",
    "groq": "GROQ_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "cohere": "CO_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "xai": "XAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


def provider_key_env(model: str) -> str | None:
    """Env var required for a provider-prefixed model string (None if unknown/local)."""
    if model in ("test", "function"):  # Pydantic AI's built-in keyless test models
        return None
    provider = model.split(":", 1)[0] if ":" in model else "openai"
    return PROVIDER_KEY_ENV.get(provider)


def model_available(model) -> tuple[bool, str]:
    """Whether the configured model can be used: a Model instance always can; a
    provider-prefixed string needs its API key in the environment."""
    if not isinstance(model, str):
        return True, "ok"
    env = provider_key_env(model)
    if env is None:
        return True, "ok"  # unknown/local provider: let Pydantic AI decide at run time
    if os.environ.get(env):
        return True, "ok"
    return False, f"model {model!r} requires {env} in the API environment"


class LLMDecisionOutput(BaseModel):
    """Structured output schema for the LLM (strict-mode friendly: no open dicts)."""

    hypothesis: str
    evidence: list[str] = Field(default_factory=list)
    uncertainty: str = ""
    action_type: ActionType
    temperatures: list[float] = Field(default_factory=list)
    composition: float | None = Field(
        default=None, description="Composition slice for phase-diagram MC decisions."
    )
    structure_labels: list[str] = Field(default_factory=list)
    retry_calculation_id: str | None = None
    equilibration_sweeps_factor: float | None = Field(
        default=None, description="Multiplier on equilibration sweeps when retrying."
    )
    max_scf_iterations_factor: float | None = Field(
        default=None, description="Multiplier on max SCF iterations when retrying."
    )
    electron_maxstep_factor: float | None = Field(
        default=None, description="Multiplier on electron_maxstep for a DFT SCF retry."
    )
    mixing_beta_factor: float | None = Field(
        default=None, description="Multiplier on mixing_beta for a DFT SCF retry (<1 = gentler)."
    )
    reason_for_change: str | None = None
    expected_information_gain: str = ""
    stopping_rationale: str | None = None


class LLMDecider:
    name = "agent"
    kind = "llm"

    def __init__(
        self,
        instructions: str,
        render_state: Callable[[BaseScientificState], str],
        action_types: Sequence[ActionType],
        model=None,
    ):
        from ..config import get_settings

        self.instructions = instructions
        self.render_state = render_state
        self.action_types = tuple(action_types)
        self.model = model if model is not None else get_settings().agent_model
        self.last_usage: dict | None = None

    @staticmethod
    def available(model: str | None = None) -> bool:
        from ..config import get_settings

        return model_available(model if model is not None else get_settings().agent_model)[0]

    async def decide(self, state: BaseScientificState) -> ScientificDecision:
        ok, reason = model_available(self.model)
        if not ok:
            raise RuntimeError(f"strategy 'agent' unavailable: {reason}")
        # Hard guarantees stay in code: budget exhaustion always stops the loop.
        stop = check_stopping(state)
        if stop is not None and state.budget_remaining <= 0:
            return stop

        from pydantic_ai import Agent

        agent = Agent(
            self.model,
            output_type=LLMDecisionOutput,
            instructions=self.instructions,
            name="gibbs-scientist",
            retries=2,
        )
        _register_tools(agent, state)
        result = await agent.run(self.render_state(state))
        usage = result.usage
        if callable(usage):  # older Pydantic AI exposed usage() as a method
            usage = usage()
        self.last_usage = {
            "input_tokens": getattr(usage, "input_tokens", None),
            "output_tokens": getattr(usage, "output_tokens", None),
            "requests": getattr(usage, "requests", None),
        }

        out: LLMDecisionOutput = result.output
        action_type = out.action_type
        run_types = {ActionType.RUN_MONTE_CARLO, ActionType.RUN_STRUCTURE_ENERGY}
        if action_type in run_types and action_type not in self.action_types:
            action_type = self.action_types[0]

        adjusted: dict[str, float] = {}
        if out.equilibration_sweeps_factor:
            adjusted["n_equilibration_sweeps_factor"] = out.equilibration_sweeps_factor
        if out.max_scf_iterations_factor:
            adjusted["max_scf_iterations_factor"] = out.max_scf_iterations_factor
        if out.electron_maxstep_factor:
            adjusted["electron_maxstep_factor"] = out.electron_maxstep_factor
        if out.mixing_beta_factor:
            adjusted["mixing_beta_factor"] = out.mixing_beta_factor

        return ScientificDecision(
            source="llm",
            hypothesis=out.hypothesis,
            evidence=out.evidence,
            uncertainty=out.uncertainty,
            action_type=action_type,
            temperatures=out.temperatures,
            composition=out.composition,
            structure_labels=out.structure_labels,
            retry_calculation_id=out.retry_calculation_id,
            adjusted_parameters=adjusted or None,
            reason_for_change=out.reason_for_change,
            expected_information_gain=out.expected_information_gain,
            stopping_rationale=out.stopping_rationale,
        )


def _register_tools(agent, state: BaseScientificState) -> None:
    """Deterministic inspection tools, chosen by what the state exposes."""

    if hasattr(state, "acquisition_state"):  # Ising V0

        @agent.tool_plain
        def get_surrogate_curve() -> str:
            """Predicted susceptibility curve chi(T) with ensemble uncertainty, as JSON."""
            surrogate = state.acquisition_state().surrogate(seed=0)
            if surrogate is None:
                return json.dumps({"error": "fewer than 3 measurements; no surrogate yet"})
            import numpy as np

            grid = np.linspace(state.temperature_min, state.temperature_max, 41)
            pred = surrogate.predict(grid)
            est = surrogate.estimate_peak(state.temperature_min, state.temperature_max)
            return json.dumps(
                {
                    "temperatures": [round(t, 4) for t in pred.temperatures],
                    "chi_mean": [round(v, 3) for v in pred.mean],
                    "chi_std": [round(v, 3) for v in pred.std],
                    "tc_estimate": {"mean": round(est.mean, 4), "std": round(est.std, 4)},
                }
            )

    if hasattr(state, "pool_predictions"):  # Alloy V1 / FCC V2 / DFT V3 / property

        @agent.tool_plain
        def get_pool_predictions() -> str:
            """Full structure pool with predicted formation energies and uncertainties, as JSON."""
            return json.dumps(
                [
                    {
                        "label": p.label,
                        "x": round(p.x, 4),
                        "e_form_pred": (
                            round(p.e_form_mean, 4) if p.e_form_mean is not None else None
                        ),
                        "e_form_std": (
                            round(p.e_form_std, 4) if p.e_form_std is not None else None
                        ),
                        "measured": p.measured,
                        "predicted_stable": p.predicted_stable,
                    }
                    for p in state.pool_predictions
                ]
            )
