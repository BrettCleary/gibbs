"""Request authentication against Better Auth sessions.

The Next.js app (apps/web) owns sign-in and writes sessions to
``app_auth.session``; this module validates the session token that the browser
attaches to API requests. A token is accepted from, in order:

1. ``Authorization: Bearer <token>`` (the normal path — set by the web client
   from the ``set-auth-token`` header Better Auth's ``bearer`` plugin emits),
2. the Better Auth session cookie (same-site deployments),
3. ``?token=`` on ``text/event-stream`` requests only — ``EventSource`` cannot
   set headers.

Better Auth tokens have the form ``<raw>.<hmac>``; the database stores ``raw``.
The raw part is 32 random bytes, so the row lookup alone authenticates the
request (the HMAC only exists to short-circuit DB hits inside Better Auth).
"""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import unquote

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import AuthSession, AuthUser
from .deps import get_session

SESSION_COOKIES = ("better-auth.session_token", "__Secure-better-auth.session_token")


def _raw_token(value: str | None) -> str | None:
    if not value:
        return None
    value = unquote(value.strip())
    raw = value.split(".", 1)[0]
    return raw or None


def extract_token(request: Request) -> str | None:
    auth_header = request.headers.get("authorization", "")
    if auth_header[:7].lower() == "bearer ":
        return _raw_token(auth_header[7:])
    for name in SESSION_COOKIES:
        if cookie := request.cookies.get(name):
            return _raw_token(cookie)
    if "text/event-stream" in request.headers.get("accept", ""):
        return _raw_token(request.query_params.get("token"))
    return None


async def require_user(
    request: Request, session: AsyncSession = Depends(get_session)
) -> AuthUser:
    """Resolve the authenticated user or raise 401."""
    token = extract_token(request)
    if token is None:
        raise HTTPException(status_code=401, detail="not authenticated")
    row = (
        await session.execute(
            select(AuthUser)
            .join(AuthSession, AuthSession.user_id == AuthUser.id)
            .where(AuthSession.token == token)
            .where(AuthSession.expires_at > datetime.now(timezone.utc))
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=401, detail="invalid or expired session")
    request.state.user = row
    return row
