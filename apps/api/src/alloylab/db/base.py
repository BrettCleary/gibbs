from __future__ import annotations

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# Postgres schemas owned by the Drizzle migrations (apps/web/db/schema/schemas.ts).
SCHEMAS = ("science", "agent", "benchmarks", "app_auth")


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine(database_url: str | None = None) -> AsyncEngine:
    global _engine, _session_factory
    if _engine is None:
        from ..config import get_settings

        url = database_url or get_settings().database_url
        parsed = make_url(url)
        connect_args: dict = {}
        if parsed.drivername.startswith("sqlite"):
            connect_args = {"timeout": 30}
        elif parsed.port == 6543:
            # Supavisor's transaction pooler puts a different backend behind the
            # socket each transaction, so asyncpg cannot reuse the server-side
            # prepared statements it caches per connection.
            connect_args = {"statement_cache_size": 0}
        # pool_pre_ping: Supabase's pooler reaps idle connections, so a pooled
        # connection can be dead by the time the next request checks it out.
        _engine = create_async_engine(
            url, echo=False, connect_args=connect_args, pool_pre_ping=True
        )
        if _engine.dialect.name == "sqlite":
            # SQLite has no schemas: map science/agent/benchmarks onto "main".
            _engine = _engine.execution_options(
                schema_translate_map={name: None for name in SCHEMAS}
            )
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        get_engine()
    assert _session_factory is not None
    return _session_factory


async def init_db(database_url: str | None = None) -> None:
    """Prepare the database.

    Postgres (Supabase): the schema is owned by Drizzle migrations
    (apps/web/migrations, `pnpm --filter @alloylab/web db:migrate`); we only
    verify the tables exist and fail with a clear message otherwise.
    SQLite (tests / zero-config dev): tables are created from the mirrored
    SQLAlchemy models.
    """
    from sqlalchemy import inspect

    from . import models  # noqa: F401  (register tables)

    engine = get_engine(database_url)
    if engine.dialect.name == "sqlite":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        return
    async with engine.connect() as conn:
        existing: set[str] = set()
        for schema in SCHEMAS:
            names = await conn.run_sync(
                lambda sync, schema=schema: inspect(sync).get_table_names(schema=schema)
            )
            existing.update(f"{schema}.{n}" for n in names)
    missing = sorted(set(Base.metadata.tables) - existing)
    if missing:
        raise RuntimeError(
            f"database is missing tables {missing}; apply the Drizzle migrations first: "
            "pnpm --filter @alloylab/web db:migrate (DATABASE_URL must point at the same database)"
        )


async def dispose_db() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
