"""Benchmark mode: compare experiment-selection strategies with known ground truth."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from alloyscience.benchmark import compute_ground_truth, make_strategy, run_benchmark

from ..db.base import get_session_factory
from ..db.models import BenchmarkRun
from ..schemas import BenchmarkCreate, BenchmarkRead
from .deps import get_session

router = APIRouter(prefix="/benchmarks", tags=["benchmarks"])

_tasks: dict[str, asyncio.Task] = {}


@router.post("", response_model=BenchmarkRead, status_code=201)
async def create_benchmark(body: BenchmarkCreate, session: AsyncSession = Depends(get_session)):
    strategies = [s.value for s in body.strategies]
    if "agent" in strategies:
        raise HTTPException(
            status_code=400,
            detail="benchmark the LLM agent by running an 'agent'-strategy campaign; "
            "this endpoint compares the deterministic baselines",
        )
    run = BenchmarkRun(config=body.model_dump(mode="json"))
    session.add(run)
    await session.commit()
    _tasks[run.id] = asyncio.create_task(_execute(run.id, body))
    return run


@router.get("", response_model=list[BenchmarkRead])
async def list_benchmarks(session: AsyncSession = Depends(get_session)):
    rows = await session.execute(select(BenchmarkRun).order_by(BenchmarkRun.created_at.desc()))
    return rows.scalars().all()


@router.get("/{benchmark_id}", response_model=BenchmarkRead)
async def get_benchmark(benchmark_id: str, session: AsyncSession = Depends(get_session)):
    run = await session.get(BenchmarkRun, benchmark_id)
    if run is None:
        raise HTTPException(status_code=404, detail="benchmark not found")
    return run


async def _execute(benchmark_id: str, config: BenchmarkCreate) -> None:
    session_factory = get_session_factory()
    try:
        ground_truth = await asyncio.to_thread(
            compute_ground_truth,
            lattice_size=config.lattice_size,
            t_min=config.temperature_min,
            t_max=config.temperature_max,
        )
        results = []
        for strategy_name in [s.value for s in config.strategies]:
            for seed in config.seeds:
                result = await asyncio.to_thread(
                    run_benchmark,
                    make_strategy(strategy_name, seed=seed),
                    config.budget,
                    ground_truth,
                    None,
                    seed,
                )
                results.append(result.to_dict())

        summary: dict = {"tc_true": ground_truth.tc, "per_strategy": {}}
        for strategy_name in {r["strategy"] for r in results}:
            errors = [r["tc_error"] for r in results if r["strategy"] == strategy_name]
            stds = [r["tc_std"] for r in results if r["strategy"] == strategy_name]
            summary["per_strategy"][strategy_name] = {
                "mean_tc_error": sum(errors) / len(errors),
                "max_tc_error": max(errors),
                "mean_tc_std": sum(stds) / len(stds),
                "n_runs": len(errors),
            }

        async with session_factory() as session:
            run = await session.get(BenchmarkRun, benchmark_id)
            if run is not None:
                run.status = "COMPLETED"
                run.results = results
                run.summary = summary
                run.completed_at = datetime.now(timezone.utc)
                await session.commit()
    except Exception as exc:  # noqa: BLE001
        async with session_factory() as session:
            run = await session.get(BenchmarkRun, benchmark_id)
            if run is not None:
                run.status = "FAILED"
                run.error = str(exc)
                run.completed_at = datetime.now(timezone.utc)
                await session.commit()
