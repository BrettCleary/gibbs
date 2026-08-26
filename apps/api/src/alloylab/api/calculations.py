from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Calculation
from ..schemas import CalculationRead
from .deps import get_session

router = APIRouter(prefix="/calculations", tags=["calculations"])

MAX_LOG_BYTES = 400_000


@router.get("/{calculation_id}/log", response_class=PlainTextResponse)
async def get_calculation_log(calculation_id: str, session: AsyncSession = Depends(get_session)):
    """Raw engine log artifact (e.g. the pw.x output) for the run inspector."""
    calc = await session.get(Calculation, calculation_id)
    if calc is None:
        raise HTTPException(status_code=404, detail="calculation not found")
    if not calc.stdout_artifact:
        raise HTTPException(status_code=404, detail="calculation has no log artifact")
    path = Path(calc.stdout_artifact)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="log artifact file is missing")
    data = path.read_bytes()
    if len(data) > MAX_LOG_BYTES:
        data = b"[... truncated ...]\n" + data[-MAX_LOG_BYTES:]
    return data.decode(errors="replace")


@router.get("/{calculation_id}", response_model=CalculationRead)
async def get_calculation(calculation_id: str, session: AsyncSession = Depends(get_session)):
    calc = await session.get(Calculation, calculation_id)
    if calc is None:
        raise HTTPException(status_code=404, detail="calculation not found")
    return calc


@router.get("/{calculation_id}/retries", response_model=list[CalculationRead])
async def get_retries(calculation_id: str, session: AsyncSession = Depends(get_session)):
    rows = await session.execute(
        select(Calculation)
        .where(Calculation.retry_of == calculation_id)
        .order_by(Calculation.created_at)
    )
    return rows.scalars().all()
