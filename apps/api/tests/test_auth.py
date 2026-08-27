"""Session validation against the Better Auth tables (gibbs.api.auth)."""

from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

import gibbs.db.base as db_base
from gibbs.config import get_settings
from gibbs.db.models import AuthSession, AuthUser


@pytest.fixture
async def unauth_client(tmp_path, monkeypatch):
    """App with the real auth dependency (no override) and one seeded session."""
    monkeypatch.setenv("ALLOYLAB_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/test.db")
    get_settings.cache_clear()
    await db_base.dispose_db()
    await db_base.init_db()

    async with db_base.get_session_factory()() as s:
        s.add(AuthUser(id="u1", name="Ada", email="ada@example.com"))
        s.add(
            AuthSession(
                id="s1",
                token="validtoken",
                user_id="u1",
                expires_at=datetime.now(timezone.utc) + timedelta(days=1),
            )
        )
        s.add(
            AuthSession(
                id="s2",
                token="expiredtoken",
                user_id="u1",
                expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            )
        )
        await s.commit()

    from gibbs.agent.loop import runner_registry
    from gibbs.main import create_app

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

    await runner_registry.shutdown()
    await db_base.dispose_db()
    get_settings.cache_clear()


async def test_health_is_public(unauth_client):
    assert (await unauth_client.get("/health")).status_code == 200


@pytest.mark.parametrize("path", ["/campaigns", "/benchmarks", "/calculations/x"])
async def test_endpoints_reject_anonymous(unauth_client, path):
    r = await unauth_client.get(path)
    assert r.status_code == 401
    r = await unauth_client.post("/campaigns", json={"name": "x"})
    assert r.status_code == 401


async def test_bearer_token_signed_form(unauth_client):
    r = await unauth_client.get("/campaigns", headers={"Authorization": "Bearer validtoken.somesignature"})
    assert r.status_code == 200
    r = await unauth_client.get("/campaigns", headers={"Authorization": "Bearer validtoken"})
    assert r.status_code == 200


async def test_invalid_and_expired_tokens(unauth_client):
    for token in ("nope", "expiredtoken.sig"):
        r = await unauth_client.get("/campaigns", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401, token


async def test_session_cookie(unauth_client):
    unauth_client.cookies.set("better-auth.session_token", "validtoken.sig")
    r = await unauth_client.get("/campaigns")
    assert r.status_code == 200


async def test_query_token_only_for_event_streams(unauth_client):
    r = await unauth_client.get("/campaigns", params={"token": "validtoken"})
    assert r.status_code == 401
    # Any route accepts the query token when the client negotiates an event stream
    # (the real /events route streams forever, so use a plain one here).
    r = await unauth_client.get(
        "/campaigns/missing/agent-events",
        params={"token": "validtoken"},
        headers={"Accept": "text/event-stream"},
    )
    assert r.status_code == 404
