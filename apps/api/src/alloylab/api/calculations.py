from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Calculation
from ..schemas import CalculationRead
from .deps import get_session

router = APIRouter(prefix="/calculations", tags=["calculations"])


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
