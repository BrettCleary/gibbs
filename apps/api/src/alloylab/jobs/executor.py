"""Async job executor for simulation calculations.

This is the V0/V1 stand-in for Temporal (plan section 11): jobs are strongly
typed rows in the `calculations` table, executed in worker threads with status
transitions, provenance, categorised failures, and live events. The agent
never runs shell commands — it only submits typed jobs through this layer.

Engines:
  MONTE_CARLO       -> alloyscience.ising.IsingSimulator
  STRUCTURE_ENERGY  -> alloyscience.alloy.StructureOracle (hidden Hamiltonian
                       read from campaign.problem_config; never shown to the agent)
"""

from __future__ import annotations

import asyncio
import zlib
from datetime import datetime, timezone

import numpy as np
from sqlalchemy import select

from alloyscience.alloy import AlloyStructure, HiddenPairHamiltonian, StructureOracle
from alloyscience.errors import SimulationFailure
from alloyscience.ising import IsingSimulator

from ..db.base import get_session_factory
from ..db.models import Calculation, Campaign
from ..events import emit_agent_event


def _now() -> datetime:
    return datetime.now(timezone.utc)


class JobExecutor:
    def __init__(self, max_concurrent: int = 2):
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def run_calculation(self, calculation_id: str) -> Calculation:
        """Execute one queued calculation to completion (SUCCEEDED or FAILED)."""
        async with self._semaphore:
            session_factory = get_session_factory()
            async with session_factory() as session:
                calc = (
                    await session.execute(
                        select(Calculation).where(Calculation.id == calculation_id)
                    )
                ).scalar_one()
                campaign = await session.get(Campaign, calc.campaign_id)
                problem_config = (campaign.problem_config or {}) if campaign else {}
                calc.status = "RUNNING"
                calc.started_at = _now()
                await session.commit()
                await emit_agent_event(
                    session,
                    calc.campaign_id,
                    "JOB_STARTED",
                    action=_start_text(calc),
                    tool_output_reference=f"calculation:{calc.id}",
                )

                params = dict(calc.input_parameters)
                try:
                    output, provenance = await asyncio.to_thread(
                        _execute, calc.calculation_type, calc.id, params, problem_config
                    )
                    calc.status = "SUCCEEDED"
                    calc.completed_at = _now()
                    calc.output = output
                    calc.provenance = {
                        **provenance,
                        "engine": calc.engine,
                        "input_parameters": params,
                        "seed": params.get("seed"),
                    }
                    await session.commit()
                    await emit_agent_event(
                        session,
                        calc.campaign_id,
                        "JOB_SUCCEEDED",
                        action=_success_text(calc),
                        tool_output_reference=f"calculation:{calc.id}",
                        payload=_success_payload(calc),
                    )
                except SimulationFailure as failure:
                    calc.status = "FAILED"
                    calc.completed_at = _now()
                    calc.failure_category = failure.category
                    calc.failure_metadata = failure.metadata
                    await session.commit()
                    await emit_agent_event(
                        session,
                        calc.campaign_id,
                        "JOB_FAILED",
                        action=f"Run failed: {failure.category}",
                        tool_output_reference=f"calculation:{calc.id}",
                        payload={"failure_category": failure.category, **failure.metadata},
                    )
                return calc


def _execute(
    calculation_type: str, calculation_id: str, params: dict, problem_config: dict
) -> tuple[dict, dict]:
    """Runs in a worker thread; returns (output, provenance)."""
    if calculation_type == "MONTE_CARLO":
        return _execute_monte_carlo(calculation_id, params)
    if calculation_type == "STRUCTURE_ENERGY":
        return _execute_structure_energy(params, problem_config)
    raise SimulationFailure(
        category="UNSUPPORTED_CALCULATION",
        message=f"no engine for calculation type {calculation_type!r}",
        metadata={"calculation_type": calculation_type},
    )


def _execute_monte_carlo(calculation_id: str, params: dict) -> tuple[dict, dict]:
    failure_rate = float(params.get("failure_rate", 0.0))
    is_retry = bool(params.get("is_retry", False))
    if failure_rate > 0 and not is_retry:
        # Deterministic per-calculation roll so reruns reproduce (crc32, not
        # hash(): Python string hashing is randomised per process).
        roll_rng = np.random.default_rng(zlib.crc32(calculation_id.encode()))
        if roll_rng.random() < failure_rate:
            raise SimulationFailure(
                category="MC_NOT_EQUILIBRATED",
                message="Monte Carlo chain flagged as not equilibrated "
                "(injected failure for recovery testing)",
                metadata={
                    "temperature": params.get("temperature"),
                    "n_equilibration_sweeps": params.get("n_equilibration_sweeps"),
                    "hint": "increase equilibration sweeps and retry",
                },
            )
    simulator = IsingSimulator(int(params["lattice_size"]))
    result = simulator.run(
        float(params["temperature"]),
        n_equilibration_sweeps=int(params.get("n_equilibration_sweeps", 800)),
        n_measurement_sweeps=int(params.get("n_measurement_sweeps", 2000)),
        seed=int(params.get("seed", 0)),
    )
    return result.to_dict(), {**result.provenance, "wall_time_s": result.wall_time_s}


class _FeatureStructure:
    """Minimal structure shim for oracles that only need the CE design row."""

    def __init__(self, label: str, features: list[float]):
        self.label = label
        self._features = np.array(features, dtype=float)

    def feature_vector(self) -> np.ndarray:
        return self._features


def _execute_structure_energy(params: dict, problem_config: dict) -> tuple[dict, dict]:
    kind = problem_config.get("kind", "pair_hamiltonian")
    if kind == "fcc_ce":
        from alloyscience.fcc import HiddenFccCE

        hidden = HiddenFccCE.from_dict(problem_config.get("hamiltonian", {}))
        structure = _FeatureStructure(str(params["structure_label"]), params["features"])
        engine_detail = "hidden icet cluster-expansion oracle (ECIs withheld from agent)"
    else:
        hidden = HiddenPairHamiltonian.from_dict(problem_config.get("hamiltonian", {}))
        structure = AlloyStructure(
            label=str(params["structure_label"]),
            occupations=tuple(tuple(int(v) for v in row) for row in params["occupations"]),
            shape=(int(params["shape"][0]), int(params["shape"][1])),
            x=float(params["composition"]),
            n_sites=int(params["n_sites"]),
            features=tuple(float(f) for f in params["features"]),
        )
        engine_detail = "hidden pair Hamiltonian oracle (parameters withheld from agent)"
    oracle = StructureOracle(
        hidden,
        failure_rate=float(params.get("failure_rate", 0.0)),
        seed=int(problem_config.get("oracle_seed", 0)),
    )
    energy = oracle.evaluate(
        structure,
        query_seed=int(params.get("seed", 0)),
        is_retry=bool(params.get("is_retry", False)),
    )
    output = {
        "energy_per_site": float(energy),
        "structure_label": str(params["structure_label"]),
        "composition": float(params["composition"]),
    }
    provenance = {
        "engine_detail": engine_detail,
        "noise_model": "gaussian, deterministic per (structure, seed)",
    }
    return output, provenance


def _start_text(calc: Calculation) -> str:
    p = calc.input_parameters
    if calc.calculation_type == "MONTE_CARLO":
        return f"Monte Carlo run started at T={float(p.get('temperature', 0.0)):.3f}"
    return (
        f"Oracle energy query started for {p.get('structure_label', '?')} "
        f"(x={float(p.get('composition', 0.0)):.3f})"
    )


def _success_text(calc: Calculation) -> str:
    p = calc.input_parameters
    out = calc.output or {}
    if calc.calculation_type == "MONTE_CARLO":
        return (
            f"T={float(p.get('temperature', 0.0)):.3f}: "
            f"chi={out.get('susceptibility', 0.0):.2f}±{out.get('susceptibility_err', 0.0):.2f}"
        )
    return f"{out.get('structure_label', '?')}: E/site = {out.get('energy_per_site', 0.0):.4f}"


def _success_payload(calc: Calculation) -> dict:
    out = calc.output or {}
    if calc.calculation_type == "MONTE_CARLO":
        return {"susceptibility": out.get("susceptibility")}
    return {
        "energy_per_site": out.get("energy_per_site"),
        "structure_label": out.get("structure_label"),
    }
