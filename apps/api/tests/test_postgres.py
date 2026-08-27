"""Supabase/Postgres integration: the Python API running against a database
whose schema was created by the Drizzle migrations (apps/web/migrations).

Set ALLOYLAB_TEST_DATABASE_URL (postgresql+asyncpg://...) to a migrated
database to run; e.g. the local Supabase stack or infra/docker Postgres."""

import asyncio
import os

import pytest
from httpx import ASGITransport, AsyncClient

import gibbs.db.base as db_base
from gibbs.config import get_settings

PG_URL = os.environ.get("ALLOYLAB_TEST_DATABASE_URL")


@pytest.fixture
async def pg_client(monkeypatch):
    if not PG_URL:
        pytest.skip("set ALLOYLAB_TEST_DATABASE_URL to a Drizzle-migrated Postgres")
    monkeypatch.setenv("ALLOYLAB_DATABASE_URL", PG_URL)
    get_settings.cache_clear()
    await db_base.dispose_db()
    await db_base.init_db()  # verifies the Drizzle-created tables exist
    from gibbs.agent.loop import runner_registry
    from gibbs.main import create_app

    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as c:
        yield c
    await runner_registry.shutdown()
    await db_base.dispose_db()
    get_settings.cache_clear()


async def test_campaign_round_trip_on_postgres(pg_client):
    from gibbs.agent.loop import runner_registry

    r = await pg_client.post(
        "/campaigns",
        json={"name": "pg ising", "strategy": "grid", "simulation_budget": 4, "lattice_size": 8},
    )
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    r = await pg_client.post(f"/campaigns/{cid}/start")
    assert r.status_code == 200, r.text
    await asyncio.wait_for(runner_registry.wait(cid), timeout=120)
    campaign = (await pg_client.get(f"/campaigns/{cid}")).json()
    assert campaign["status"] == "COMPLETED"
    assert campaign["simulations_used"] == 4
    calcs = (await pg_client.get(f"/campaigns/{cid}/calculations")).json()
    assert len(calcs) == 4 and all(c["output"]["susceptibility"] >= 0 for c in calcs)
    # jsonb round-trips nested output/provenance intact.
    assert isinstance(calcs[0]["provenance"], dict) and "engine" in calcs[0]["provenance"]
    models = (await pg_client.get(f"/campaigns/{cid}/models")).json()
    assert models and len(models[-1]["artifact"]["temperatures"]) == 101
    report = (await pg_client.get(f"/campaigns/{cid}/report")).json()
    assert report["status"] == "COMPLETED"


async def test_alloy_campaign_on_postgres(pg_client):
    from gibbs.agent.loop import runner_registry

    r = await pg_client.post(
        "/campaigns",
        json={"name": "pg alloy", "problem_type": "alloy_v1", "strategy": "uncertainty",
              "simulation_budget": 8},
    )
    cid = r.json()["id"]
    await pg_client.post(f"/campaigns/{cid}/start")
    await asyncio.wait_for(runner_registry.wait(cid), timeout=180)
    hull = (await pg_client.get(f"/campaigns/{cid}/hull")).json()
    assert hull["endpoints_measured"] and len(hull["points"]) >= 30
    structures = (await pg_client.get(f"/campaigns/{cid}/structures")).json()
    assert structures and isinstance(structures[0]["occupations"], list)
