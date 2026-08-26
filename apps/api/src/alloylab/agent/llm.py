"""LLM scientist decider built on the OpenAI Agents SDK.

The LLM chooses experiments and interprets results; it never computes numbers.
All quantities it sees come from the deterministic tools/state, and its output
is forced into a structured decision schema that the loop validates.
"""

from __future__ import annotations

import json
import os

from pydantic import BaseModel, Field

from .decisions import ActionType, ScientificDecision
from .state import ScientificState
from .strategies import check_stopping

INSTRUCTIONS = """\
You are an autonomous computational materials scientist running a Monte Carlo
campaign on the 2D Ising model. Your objective: locate the critical-temperature
region (the susceptibility peak) as precisely as possible within a finite
simulation budget.

Rules:
- You never compute physical quantities yourself; every number you cite must
  come from the provided state or tools.
- Prefer measurements that most reduce uncertainty about the susceptibility
  peak location. Early on, cover the temperature range; later, concentrate
  around the suspected peak and wherever the surrogate ensemble disagrees.
- If a calculation failed and has not been resolved, decide whether to RETRY
  it (typically with longer equilibration) or ABANDON it. A run that already
  failed once as a retry should be abandoned.
- Propose at most 3 temperatures per decision and stay inside the allowed range.
- If the budget is exhausted, or the Tc uncertainty is below the target, or you
  judge further experiments to have low expected value, FINISH the campaign and
  say why.
- Fill hypothesis / evidence / uncertainty / expected_information_gain with
  concise, concrete scientific statements grounded in the numbers you saw.
"""


class LLMDecisionOutput(BaseModel):
    """Structured output schema for the LLM (strict-mode friendly: no open dicts)."""

    hypothesis: str
    evidence: list[str] = Field(default_factory=list)
    uncertainty: str = ""
    action_type: ActionType
    temperatures: list[float] = Field(default_factory=list)
    retry_calculation_id: str | None = None
    equilibration_sweeps_factor: float | None = Field(
        default=None, description="Multiplier on equilibration sweeps when retrying."
    )
    reason_for_change: str | None = None
    expected_information_gain: str = ""
    stopping_rationale: str | None = None


class LLMDecider:
    name = "agent"

    def __init__(self, model: str | None = None):
        from ..config import get_settings

        self.model = model or get_settings().agent_model
        self.last_usage: dict | None = None

    @staticmethod
    def available() -> bool:
        return bool(os.environ.get("OPENAI_API_KEY"))

    async def decide(self, state: ScientificState) -> ScientificDecision:
        if not self.available():
            raise RuntimeError(
                "strategy 'agent' requires OPENAI_API_KEY; choose a heuristic strategy "
                "(random/grid/uncertainty) or set the key"
            )
        # Hard guarantees stay in code: budget exhaustion always stops the loop.
        stop = check_stopping(state)
        if stop is not None and state.budget_remaining <= 0:
            return stop

        from agents import Agent, Runner, function_tool

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

        agent = Agent(
            name="alloylab-scientist",
            instructions=INSTRUCTIONS,
            model=self.model,
            output_type=LLMDecisionOutput,
            tools=[get_surrogate_curve],
        )
        result = await Runner.run(agent, input=self._render_state(state))
        try:
            usage = result.context_wrapper.usage
            self.last_usage = {
                "input_tokens": getattr(usage, "input_tokens", None),
                "output_tokens": getattr(usage, "output_tokens", None),
            }
        except AttributeError:
            self.last_usage = None

        out: LLMDecisionOutput = result.final_output
        return ScientificDecision(
            hypothesis=out.hypothesis,
            evidence=out.evidence,
            uncertainty=out.uncertainty,
            action_type=out.action_type,
            temperatures=out.temperatures,
            retry_calculation_id=out.retry_calculation_id,
            adjusted_parameters=(
                {"n_equilibration_sweeps_factor": out.equilibration_sweeps_factor}
                if out.equilibration_sweeps_factor
                else None
            ),
            reason_for_change=out.reason_for_change,
            expected_information_gain=out.expected_information_gain,
            stopping_rationale=out.stopping_rationale,
        )

    def _render_state(self, state: ScientificState) -> str:
        measurements = [
            {
                "calculation_id": m.calculation_id,
                "T": round(m.temperature, 4),
                "chi": round(m.susceptibility, 3),
                "chi_err": round(m.susceptibility_err, 3),
            }
            for m in state.measurements
        ]
        payload = {
            "objective": state.objective,
            "temperature_range": [state.temperature_min, state.temperature_max],
            "lattice_size": state.lattice_size,
            "budget": {
                "total": state.budget_total,
                "used": state.budget_used,
                "remaining": state.budget_remaining,
            },
            "target_tc_uncertainty": state.target_uncertainty,
            "measurements": measurements,
            "unresolved_failures": [f.model_dump() for f in state.unresolved_failures],
            "latest_surrogate": state.latest_model.model_dump() if state.latest_model else None,
            "highest_uncertainty_temperature_suggestion": state.suggested_uncertainty_temperature,
        }
        return (
            "Current scientific state (all numbers computed by deterministic tools):\n"
            + json.dumps(payload, indent=2)
            + "\nDecide the next action."
        )
