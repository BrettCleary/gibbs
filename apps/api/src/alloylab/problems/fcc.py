"""FCC Ni-Al problem adapter (Milestone 4, plan section 22 V2): icet-backed.

Real crystallography via ASE + icet — symmetry-enumerated FCC orderings,
cluster-space cluster vectors as the CE design rows — with a hidden icet-style
cluster expansion as the ground-truth oracle. Everything else (state building,
decision validation, CE fitting with bootstrap uncertainty + LOOCV, hull
construction, failure policy, budget) is inherited from the alloy adapter:
only the pool source and the design-row definition differ.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Campaign, Structure
from ..events import emit_agent_event
from .alloy import AlloyProblem, _load_pool

FCC_LLM_INSTRUCTIONS = """\
You are an autonomous computational materials scientist searching FCC {elements}
orderings. A hidden cluster expansion governs structure energies; you can only
learn it through expensive per-structure energy queries (a simulated DFT
oracle). Your objective: identify which ordered structures are
thermodynamically stable (on the formation-energy convex hull) using as few
queries as possible. Ordered phases such as L1_2 A3B (x = 0.25), L1_0 AB (x = 0.5) and L1_2 AB3
(x = 0.75) are physically plausible candidates, but only the data decides.

Rules:
- You never compute physical quantities yourself; every number you cite must
  come from the provided state or tools.
- A cluster expansion over icet cluster vectors is refit after each batch; its
  per-structure uncertainty (ensemble std) and LOOCV error tell you where the
  model is weak.
- Prioritise queries that discriminate the hull: structures predicted near or
  below the hull with high uncertainty, and compositions with no measurements.
- If a calculation failed and has not been resolved, decide whether to RETRY
  it or ABANDON it. A run that already failed once as a retry should be abandoned.
- Propose at most 3 structure labels per decision (action_type
  RUN_STRUCTURE_ENERGY), chosen from the unmeasured pool.
- If the budget is exhausted, or the predicted stable set is confidently
  resolved, FINISH the campaign and say why.
- Fill hypothesis / evidence / uncertainty / expected_information_gain with
  concise, concrete scientific statements grounded in the numbers you saw.
"""


@dataclass(frozen=True)
class _CvPoolItem:
    """Lightweight pool item: the stored cluster vector IS the design row."""

    label: str
    x: float
    features: tuple[float, ...]

    def feature_vector(self) -> np.ndarray:
        return np.array(self.features)


class FccProblem(AlloyProblem):
    problem_type = "fcc_v2"
    llm_instructions = FCC_LLM_INSTRUCTIONS

    def pool_item(self, row: Structure) -> _CvPoolItem:
        return _CvPoolItem(
            label=row.label,
            x=float(row.composition),
            features=tuple(float(f) for f in row.features),
        )

    async def initialize(self, session: AsyncSession, campaign: Campaign) -> None:
        existing = await _load_pool(session, campaign.id)
        if existing:
            return
        from alloyscience.fcc.system import DEFAULT_MAX_SIZE, cached_system_and_pool

        x_min = campaign.composition_min if campaign.composition_min is not None else 0.0
        x_max = campaign.composition_max if campaign.composition_max is not None else 1.0
        cfg = campaign.problem_config or {}
        max_size = int(cfg.get("max_size", DEFAULT_MAX_SIZE))
        elements = tuple(cfg.get("elements", ["Ni", "Al"]))
        a_parent = float(cfg.get("a_parent", 3.52))
        from alloyscience.fcc.system import cutoffs_for

        system, full_pool = cached_system_and_pool(a_parent, cutoffs_for(a_parent), elements, max_size)
        pool = [
            s
            for s in full_pool
            if (x_min - 1e-9 <= s.x <= x_max + 1e-9) or s.x in (0.0, 1.0)
        ]
        for s in pool:
            session.add(
                Structure(
                    campaign_id=campaign.id,
                    label=s.label,
                    chemical_formula=s.chemical_formula,
                    composition=s.x,
                    n_sites=s.n_sites,
                    occupations=[],
                    shape=[],
                    features=list(s.cluster_vector),
                    lattice=[list(row) for row in s.cell],
                    positions=[list(p) for p in s.positions],
                    atomic_numbers=list(s.atomic_numbers),
                )
            )
        await session.commit()
        await emit_agent_event(
            session,
            campaign.id,
            "POOL_ENUMERATED",
            action=f"icet enumerated {len(pool)} cluster-vector-distinct FCC {elements[0]}-{elements[1]} "
            f"orderings (a = {a_parent:.3f} Å, cells up to {max_size} atoms, {system.n_parameters}-parameter "
            f"cluster space) in x_{elements[1]} ∈ [{x_min:.2f}, {x_max:.2f}]",
            payload={"n_structures": len(pool), "n_ce_parameters": system.n_parameters},
        )
