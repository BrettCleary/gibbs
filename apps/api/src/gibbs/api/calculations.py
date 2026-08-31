from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import AuthUser, Calculation, Campaign
from ..schemas import CalculationRead
from .auth import require_user
from .deps import get_session

router = APIRouter(prefix="/calculations", tags=["calculations"])

MAX_LOG_BYTES = 400_000


async def _owned_calculation(
    session: AsyncSession, calculation_id: str, user: AuthUser
) -> Calculation:
    """The calculation, if it belongs to a campaign this user owns."""
    calc = (
        await session.execute(
            select(Calculation)
            .join(Campaign, Campaign.id == Calculation.campaign_id)
            .where(Calculation.id == calculation_id, Campaign.user_id == user.id)
        )
    ).scalar_one_or_none()
    if calc is None:
        raise HTTPException(status_code=404, detail="calculation not found")
    return calc


@router.get("/{calculation_id}/log", response_class=PlainTextResponse)
async def get_calculation_log(
    calculation_id: str,
    session: AsyncSession = Depends(get_session),
    user: AuthUser = Depends(require_user),
):
    """Raw engine log artifact (e.g. the pw.x output) for the run inspector."""
    calc = await _owned_calculation(session, calculation_id, user)
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
async def get_calculation(
    calculation_id: str,
    session: AsyncSession = Depends(get_session),
    user: AuthUser = Depends(require_user),
):
    return await _owned_calculation(session, calculation_id, user)


@router.get("/{calculation_id}/retries", response_model=list[CalculationRead])
async def get_retries(
    calculation_id: str,
    session: AsyncSession = Depends(get_session),
    user: AuthUser = Depends(require_user),
):
    await _owned_calculation(session, calculation_id, user)
    rows = await session.execute(
        select(Calculation)
        .where(Calculation.retry_of == calculation_id)
        .order_by(Calculation.created_at)
    )
    return rows.scalars().all()
