"""LLM scientist decider built on the OpenAI Agents SDK.

Problem-agnostic: each problem adapter supplies its instructions, a state
renderer, and the run-action it accepts. The LLM chooses experiments and
interprets results; it never computes numbers. All quantities it sees come
from the deterministic state/tools, and its output is forced into a structured
decision schema that the problem adapter validates.
"""

from __future__ import annotations

import json
import os
from typing import Callable, Sequence

from pydantic import BaseModel, Field

from .decisions import ActionType, ScientificDecision
from .state import BaseScientificState
from .strategies import check_stopping


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
    reason_for_change: str | None = None
    expected_information_gain: str = ""
    stopping_rationale: str | None = None


class LLMDecider:
    name = "agent"

    def __init__(
        self,
        instructions: str,
        render_state: Callable[[BaseScientificState], str],
        action_types: Sequence[ActionType],
        model: str | None = None,
    ):
        from ..config import get_settings

        self.instructions = instructions
        self.render_state = render_state
        self.action_types = tuple(action_types)
        self.model = model or get_settings().agent_model
        self.last_usage: dict | None = None

    @staticmethod
    def available() -> bool:
        return bool(os.environ.get("OPENAI_API_KEY"))

    async def decide(self, state: BaseScientificState) -> ScientificDecision:
        if not self.available():
            raise RuntimeError(
                "strategy 'agent' requires OPENAI_API_KEY; choose a heuristic strategy "
                "or set the key"
            )
        # Hard guarantees stay in code: budget exhaustion always stops the loop.
        stop = check_stopping(state)
        if stop is not None and state.budget_remaining <= 0:
            return stop

        from agents import Agent, Runner

        agent = Agent(
            name="alloylab-scientist",
            instructions=self.instructions,
            model=self.model,
            output_type=LLMDecisionOutput,
            tools=_build_tools(state),
        )
        result = await Runner.run(agent, input=self.render_state(state))
        try:
            usage = result.context_wrapper.usage
            self.last_usage = {
                "input_tokens": getattr(usage, "input_tokens", None),
                "output_tokens": getattr(usage, "output_tokens", None),
            }
        except AttributeError:
            self.last_usage = None

        out: LLMDecisionOutput = result.final_output
        action_type = out.action_type
        run_types = {ActionType.RUN_MONTE_CARLO, ActionType.RUN_STRUCTURE_ENERGY}
        if action_type in run_types and action_type not in self.action_types:
            action_type = self.action_types[0]

        adjusted: dict[str, float] = {}
        if out.equilibration_sweeps_factor:
            adjusted["n_equilibration_sweeps_factor"] = out.equilibration_sweeps_factor
        if out.max_scf_iterations_factor:
            adjusted["max_scf_iterations_factor"] = out.max_scf_iterations_factor

        return ScientificDecision(
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


def _build_tools(state: BaseScientificState) -> list:
    """Deterministic inspection tools, chosen by what the state exposes."""
    from agents import function_tool

    tools = []

    if hasattr(state, "acquisition_state"):  # Ising V0

        @function_tool
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

        tools.append(get_surrogate_curve)

    if hasattr(state, "pool_predictions"):  # Alloy V1

        @function_tool
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

        tools.append(get_pool_predictions)

    return tools
