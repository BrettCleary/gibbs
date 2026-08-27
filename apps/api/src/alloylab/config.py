from __future__ import annotations

import os
from functools import lru_cache
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Postgres URIs injected by the Vercel <-> Supabase integration, in preference
# order, used when ALLOYLAB_DATABASE_URL is not set. POSTGRES_URL is the
# Supavisor pooler; POSTGRES_URL_NON_POOLING may point at db.<ref>.supabase.co,
# which is IPv6-only and unreachable from Vercel's container runtime.
PLATFORM_DATABASE_URL_VARS = ("POSTGRES_URL", "POSTGRES_URL_NON_POOLING", "DATABASE_URL")

# libpq keywords those URIs carry. SQLAlchemy's asyncpg dialect forwards every
# leftover query parameter straight into asyncpg.connect(), which raises
# TypeError on any keyword it does not know.
_LIBPQ_ONLY_PARAMS = {"supa", "pgbouncer", "connection_limit", "options", "target_session_attrs"}


def normalize_database_url(url: str) -> str:
    """Coerce a platform-provided Postgres URI into a SQLAlchemy + asyncpg one.

    Adds the async driver to the scheme, translates or drops libpq-only query
    parameters, and disables the prepared-statement cache behind Supavisor's
    transaction pooler (port 6543), which hands a different backend to every
    statement so a per-connection cache goes stale.
    """
    parts = urlsplit(url)
    if not parts.scheme.startswith("postgres"):
        return url
    scheme = parts.scheme if "+" in parts.scheme else "postgresql+asyncpg"
    if not scheme.endswith("+asyncpg"):
        return url
    query: list[tuple[str, str]] = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key == "sslmode":
            query.append(("ssl", value))  # asyncpg spells it `ssl`
        elif key not in _LIBPQ_ONLY_PARAMS:
            query.append((key, value))
    if parts.port == 6543 and not any(key == "prepared_statement_cache_size" for key, _ in query):
        query.append(("prepared_statement_cache_size", "0"))
    return urlunsplit((scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


class Settings(BaseSettings):
    """Runtime configuration. Override with ALLOYLAB_* environment variables."""

    # Supabase Postgres (schema managed by Drizzle in apps/web). The default is
    # the local Supabase stack (`supabase start`); set ALLOYLAB_DATABASE_URL to a
    # hosted project's session-pooler URI as postgresql+asyncpg://... . A
    # sqlite+aiosqlite:// URL is still accepted for zero-config dev and tests.
    database_url: str = "postgresql+asyncpg://postgres:postgres@127.0.0.1:54332/postgres"
    cors_origins: list[str] = ["http://localhost:3000"]
    max_concurrent_jobs: int = 2
    # LLM agent (Pydantic AI). Provider-prefixed model string, e.g. "openai:gpt-5",
    # "anthropic:claude-sonnet-4-5", "google-gla:gemini-2.5-pro"; the provider's
    # API key (OPENAI_API_KEY, ANTHROPIC_API_KEY, ...) must be in the environment.
    agent_model: str = "openai:gpt-5"
    # Real-DFT engine (Milestone 6).
    artifacts_dir: str = "./alloylab_data"
    pw_command: str = "pw.x"
    pseudo_dir: str = "infra/pseudopotentials"
    omp_num_threads: int = 4
    # Durable execution (Milestone 7). executor: "local" | "temporal".
    executor: str = "local"
    temporal_address: str = "localhost:7233"
    temporal_task_queue: str = "alloylab-calculations"
    job_timeout_seconds: int = 1800

    @model_validator(mode="before")
    @classmethod
    def _inherit_platform_database_url(cls, data: Any) -> Any:
        """Fall back to the host platform's Postgres URI (Vercel/Supabase)."""
        if isinstance(data, dict) and not data.get("database_url"):
            for var in PLATFORM_DATABASE_URL_VARS:
                if url := os.environ.get(var):
                    data["database_url"] = url
                    break
        return data

    @field_validator("database_url")
    @classmethod
    def _normalize_database_url(cls, value: str) -> str:
        return normalize_database_url(value)

    model_config = SettingsConfigDict(
        env_prefix="ALLOYLAB_",
        # Works from the repo root (`uv run ...`) and from apps/api (`pnpm --filter @alloylab/api dev`).
        env_file=(".env", "apps/api/.env"),
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
