import os

import pytest
from httpx import ASGITransport, AsyncClient

import gibbs.db.base as db_base
from gibbs.config import get_settings


@pytest.fixture(autouse=True)
def _no_env_files(monkeypatch):
    """Tests must never pick up the developer's real .env (provider keys etc.).

    Three separate doors have to be shut, which is why patching ENV_FILES alone
    was never enough:

    - Settings reads the file itself through model_config["env_file"], baked in
      at class creation and unaffected by the ENV_FILES module global;
    - load_env_files() exports the file into os.environ, and any module imported
      at collection time that calls get_settings() leaks it there before this
      fixture can run — nothing later can unset it;
    - the settings object itself is lru_cached.

    Without all three, a developer with ALLOYLAB_EXECUTOR=temporal in .env has
    the suite submitting work to their real Temporal namespace.
    """
    from gibbs.config import Settings

    monkeypatch.setattr("gibbs.config.ENV_FILES", ())
    monkeypatch.setitem(Settings.model_config, "env_file", ())
    # ALLOYLAB_*TEST* are the suite's own switches (opt-in Temporal round trip,
    # Postgres URL), not application config — leave those alone.
    for key in [k for k in os.environ if k.startswith("ALLOYLAB_") and "TEST" not in k]:
        monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def inject_failures(monkeypatch):
    """Enable the failure-injection seam for a test.

    Campaigns read the rate from settings at creation time (it is not a request
    parameter), so this has to be called before the POST /campaigns whose
    calculations should fail.
    """

    def _set(rate: float) -> None:
        monkeypatch.setenv("ALLOYLAB_INJECTED_FAILURE_RATE", str(rate))
        get_settings.cache_clear()

    return _set


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
