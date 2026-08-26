"""Real-DFT problem adapter (Milestone 6): the fcc hull search with a real
ASE-backed calculator instead of the hidden cluster expansion.

Engines (plan section 2.2's swap points, chosen per campaign):
  emt      — ASE effective-medium theory classical potential (fast, no install)
  espresso — Quantum ESPRESSO pw.x SCF (real DFT: minutes per structure, real
             SCF failures, log artifacts, retries with adjusted mixing/steps)

Everything else — enumeration, CE fitting with LOOCV, hull, budget, failure
policy, dashboard — is inherited unchanged from the fcc adapter. There is no
benchmark ground truth here: nature keeps its own secrets.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from ..agent.decisions import ScientificDecision
from ..agent.strategies import Decider, stable_seed
from ..db.models import Campaign
from ..events import emit_agent_event
from .alloy import AlloyHeuristicDecider, AlloyLLMDecider, _load_pool
from .fcc import FccProblem

DFT_RETRY_ADJUSTMENT = {"electron_maxstep_factor": 2.0, "mixing_beta_factor": 0.5}
DFT_RETRY_REASON = (
    "Doubled electron_maxstep and halved mixing_beta to recover SCF convergence."
)

DFT_LLM_INSTRUCTIONS = """\
You are an autonomous computational materials scientist searching FCC Ni-Al
orderings with REAL first-principles calculations. Each energy query runs an
actual DFT (or classical-potential) calculation — expensive, minutes per
structure — so every query must count. Your objective: identify which ordered
structures are thermodynamically stable (on the formation-energy convex hull)
using as few calculations as possible.

Rules:
- You never compute physical quantities yourself; every number you cite must
  come from the provided state or tools.
- A cluster expansion over icet cluster vectors is refit after each batch; its
  per-structure uncertainty (ensemble std) and LOOCV error tell you where the
  model is weak.
- Prioritise queries that discriminate the hull: structures predicted near or
  below the hull with high uncertainty, and compositions with no measurements.
- DFT calculations really do fail (SCF non-convergence). If a calculation
  failed and is unresolved, RETRY it with more SCF steps and gentler mixing,
  or ABANDON it if a retry already failed.
- Propose at most 3 structure labels per decision (action_type
  RUN_STRUCTURE_ENERGY), chosen from the unmeasured pool.
- If the budget is exhausted, or the predicted stable set is confidently
  resolved, FINISH the campaign and say why.
- Fill hypothesis / evidence / uncertainty / expected_information_gain with
  concise, concrete scientific statements grounded in the numbers you saw.
"""


class DftProblem(FccProblem):
    problem_type = "dft_v3"
    llm_instructions = DFT_LLM_INSTRUCTIONS

    def decider(self, campaign: Campaign) -> Decider:
        if campaign.strategy == "agent":
            return AlloyLLMDecider(instructions=self.llm_instructions)
        return AlloyHeuristicDecider(
            campaign.strategy,
            seed=stable_seed(campaign.id),
            retry_adjustment=self._retry_adjustment(campaign),
            retry_reason=self._retry_reason(campaign),
        )

    def _engine(self, campaign: Campaign) -> str:
        return (campaign.problem_config or {}).get("engine", "emt")

    def _retry_adjustment(self, campaign: Campaign) -> dict:
        return DFT_RETRY_ADJUSTMENT if self._engine(campaign) == "espresso" else {}

    def _retry_reason(self, campaign: Campaign) -> str:
        if self._engine(campaign) == "espresso":
            return DFT_RETRY_REASON
        return "Re-ran the calculation."

    async def initialize(self, session: AsyncSession, campaign: Campaign) -> None:
        existing = await _load_pool(session, campaign.id)
        if existing:
            return
        await super().initialize(session, campaign)
        engine = self._engine(campaign)
        await emit_agent_event(
            session,
            campaign.id,
            "ENGINE_SELECTED",
            action=(
                "Energy engine: Quantum ESPRESSO pw.x (real DFT, single-point SCF at "
                "Vegard-scaled lattice)"
                if engine == "espresso"
                else "Energy engine: ASE EMT classical potential (volume-optimised)"
            ),
            payload={"engine": engine},
        )

    async def create_calculations(
        self, session: AsyncSession, campaign: Campaign, decision: ScientificDecision
    ) -> list[str]:
        ids = await super().create_calculations(session, campaign, decision)
        # Annotate engine + retry-able SCF parameters on the job records.
        engine = self._engine(campaign)
        espresso_cfg = (campaign.problem_config or {}).get("espresso", {})
        from ..db.models import Calculation

        for calc_id in ids:
            calc = await session.get(Calculation, calc_id)
            if calc is None:
                continue
            params = dict(calc.input_parameters)
            if engine == "espresso":
                calc.engine = "quantum-espresso pw.x"
                params["electron_maxstep"] = int(espresso_cfg.get("electron_maxstep", 60))
                params["mixing_beta"] = float(espresso_cfg.get("mixing_beta", 0.4))
            else:
                calc.engine = "ase.calculators.emt.EMT"
            calc.input_parameters = params
        await session.commit()
        return ids
