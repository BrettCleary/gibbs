"""Benchmark mode: compare experiment-selection strategies with known ground truth."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from alloyscience.benchmark import (
    compute_ground_truth,
    make_strategy,
    run_alloy_benchmark,
    run_benchmark,
    run_fcc_benchmark,
)

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
        if config.problem.value == "alloy":
            results, summary = await _run_hull_problem(config, run_alloy_benchmark, "alloy")
        elif config.problem.value == "fcc":
            results, summary = await _run_hull_problem(config, run_fcc_benchmark, "fcc")
        elif config.problem.value == "phase":
            results, summary = await _run_phase(config)
        else:
            results, summary = await _run_ising(config)

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


async def _run_phase(config: BenchmarkCreate) -> tuple[list, dict]:
    """Phase-diagram benchmark: mean |Tc error| over slices vs a dense
    high-budget MC scan of the same hidden CE (fresh CE per seed, cached)."""
    from alloyscience.phase import run_phase_benchmark

    results = []
    for strategy_name in [s.value for s in config.strategies]:
        for seed in config.seeds:
            result = await asyncio.to_thread(
                run_phase_benchmark, strategy_name, config.budget, seed
            )
            results.append(result.to_dict())

    summary: dict = {"problem": "phase", "per_strategy": {}}
    for strategy_name in {r["strategy"] for r in results}:
        rows = [r for r in results if r["strategy"] == strategy_name]
        summary["per_strategy"][strategy_name] = {
            "mean_boundary_error": sum(r["boundary_error"] for r in rows) / len(rows),
            "max_boundary_error": max(r["max_boundary_error"] for r in rows),
            "n_runs": len(rows),
        }
    return results, summary


async def _run_ising(config: BenchmarkCreate) -> tuple[list, dict]:
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

    summary: dict = {"problem": "ising", "tc_true": ground_truth.tc, "per_strategy": {}}
    for strategy_name in {r["strategy"] for r in results}:
        errors = [r["tc_error"] for r in results if r["strategy"] == strategy_name]
        stds = [r["tc_std"] for r in results if r["strategy"] == strategy_name]
        summary["per_strategy"][strategy_name] = {
            "mean_tc_error": sum(errors) / len(errors),
            "max_tc_error": max(errors),
            "mean_tc_std": sum(stds) / len(stds),
            "n_runs": len(errors),
        }
    return results, summary


async def _run_hull_problem(
    config: BenchmarkCreate, runner, problem_name: str
) -> tuple[list, dict]:
    """Hull-discovery benchmark (alloy/fcc): each seed draws a fresh hidden
    Hamiltonian; strategies are scored on hull reconstruction (plan section 21)."""
    results = []
    for strategy_name in [s.value for s in config.strategies]:
        # "grid" maps to the plan's composition-coverage baseline.
        hull_strategy = "coverage" if strategy_name == "grid" else strategy_name
        for seed in config.seeds:
            result = await asyncio.to_thread(runner, hull_strategy, config.budget, seed)
            d = result.to_dict()
            d["strategy"] = strategy_name
            results.append(d)

    summary: dict = {"problem": problem_name, "per_strategy": {}}
    for strategy_name in {r["strategy"] for r in results}:
        rows = [r for r in results if r["strategy"] == strategy_name]
        summary["per_strategy"][strategy_name] = {
            "mean_hull_rmse": sum(r["hull_rmse"] for r in rows) / len(rows),
            "mean_missed_stable": sum(r["n_missed_stable"] for r in rows) / len(rows),
            "mean_false_stable": sum(r["n_false_stable"] for r in rows) / len(rows),
            "n_runs": len(rows),
        }
    return results, summary
