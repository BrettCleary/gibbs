"""Async job executor for simulation calculations.

This is the V0 stand-in for Temporal (plan section 11): jobs are strongly
typed rows in the `calculations` table, executed in worker threads with status
transitions, provenance, categorised failures, and live events. The agent
never runs shell commands — it only submits typed jobs through this layer.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import numpy as np
from sqlalchemy import select

from alloyscience.benchmark import SimulationFailure
from alloyscience.ising import IsingSimulator

from ..db.base import get_session_factory
from ..db.models import AgentEvent, Calculation
from ..events import event_bus


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
                calc.status = "RUNNING"
                calc.started_at = _now()
                await session.commit()
                await self._emit(
                    session,
                    calc,
                    "JOB_STARTED",
                    action=f"Monte Carlo run started at T={calc.input_parameters.get('temperature'):.3f}",
                )

                params = dict(calc.input_parameters)
                try:
                    result = await asyncio.to_thread(self._execute, calc.id, params)
                    calc.status = "SUCCEEDED"
                    calc.completed_at = _now()
                    calc.output = result.to_dict()
                    calc.provenance = {
                        **result.provenance,
                        "engine": calc.engine,
                        "input_parameters": params,
                        "seed": params.get("seed"),
                        "wall_time_s": result.wall_time_s,
                    }
                    await session.commit()
                    await self._emit(
                        session,
                        calc,
                        "JOB_SUCCEEDED",
                        action=(
                            f"T={result.temperature:.3f}: chi={result.susceptibility:.2f}"
                            f"±{result.susceptibility_err:.2f}"
                        ),
                        payload={"susceptibility": result.susceptibility},
                    )
                except SimulationFailure as failure:
                    calc.status = "FAILED"
                    calc.completed_at = _now()
                    calc.failure_category = failure.category
                    calc.failure_metadata = failure.metadata
                    await session.commit()
                    await self._emit(
                        session,
                        calc,
                        "JOB_FAILED",
                        action=f"Run failed: {failure.category}",
                        payload={"failure_category": failure.category, **failure.metadata},
                    )
                return calc

    def _execute(self, calculation_id: str, params: dict):
        """Runs in a worker thread. Deterministic failure injection per calculation."""
        failure_rate = float(params.get("failure_rate", 0.0))
        is_retry = bool(params.get("is_retry", False))
        if failure_rate > 0 and not is_retry:
            # Deterministic per-calculation roll so reruns reproduce.
            roll_rng = np.random.default_rng(abs(hash(calculation_id)) % (2**32))
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
        return simulator.run(
            float(params["temperature"]),
            n_equilibration_sweeps=int(params.get("n_equilibration_sweeps", 800)),
            n_measurement_sweeps=int(params.get("n_measurement_sweeps", 2000)),
            seed=int(params.get("seed", 0)),
        )

    async def _emit(
        self,
        session,
        calc: Calculation,
        event_type: str,
        action: str | None = None,
        payload: dict | None = None,
    ) -> None:
        event = AgentEvent(
            campaign_id=calc.campaign_id,
            event_type=event_type,
            action=action,
            tool_output_reference=f"calculation:{calc.id}",
            payload=payload,
        )
        session.add(event)
        await session.commit()
        await event_bus.publish(
            calc.campaign_id,
            {
                "id": event.id,
                "campaign_id": calc.campaign_id,
                "event_type": event_type,
                "action": action,
                "tool_output_reference": f"calculation:{calc.id}",
                "payload": payload,
                "created_at": event.created_at.isoformat(),
            },
        )
