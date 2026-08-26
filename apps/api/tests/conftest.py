import pytest
from httpx import ASGITransport, AsyncClient

import alloylab.db.base as db_base
from alloylab.config import get_settings


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ALLOYLAB_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/test.db")
    get_settings.cache_clear()
    await db_base.dispose_db()
    await db_base.init_db()

    from alloylab.agent.loop import runner_registry
    from alloylab.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    await runner_registry.shutdown()
    await db_base.dispose_db()
    get_settings.cache_clear()
