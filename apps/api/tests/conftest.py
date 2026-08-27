import pytest
from httpx import ASGITransport, AsyncClient

import gibbs.db.base as db_base
from gibbs.config import get_settings


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ALLOYLAB_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/test.db")
    get_settings.cache_clear()
    await db_base.dispose_db()
    await db_base.init_db()

    from gibbs.agent.loop import runner_registry
    from gibbs.api.auth import require_user
    from gibbs.db.models import AuthUser
    from gibbs.main import create_app

    app = create_app()
    # Endpoint tests exercise the routes, not sign-in: stub the auth dependency.
    app.dependency_overrides[require_user] = lambda: AuthUser(
        id="test-user", name="Test", email="test@example.com"
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    await runner_registry.shutdown()
    await db_base.dispose_db()
    get_settings.cache_clear()
