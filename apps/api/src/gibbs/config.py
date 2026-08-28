from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Annotated, Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

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


# apps/api/src/gibbs/config.py -> repo root
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
ENV_FILES = (".env", "apps/api/.env")


class Settings(BaseSettings):
    """Runtime configuration. Override with ALLOYLAB_* environment variables."""

    # Supabase Postgres (schema managed by Drizzle in apps/web). The default is
    # the local Supabase stack (`supabase start`); set ALLOYLAB_DATABASE_URL to a
    # hosted project's session-pooler URI as postgresql+asyncpg://... . A
    # sqlite+aiosqlite:// URL is still accepted for zero-config dev and tests.
    database_url: str = "postgresql+asyncpg://postgres:postgres@127.0.0.1:54332/postgres"
    # Browser origins allowed to call the API — the deployed apps/web URL in
    # production. NoDecode + the validator below so the environment variable can
    # be a plain comma-separated list as well as a JSON array.
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]
    max_concurrent_jobs: int = 2
    # LLM agent (Pydantic AI). Provider-prefixed model string, e.g. "openai:gpt-5",
    # "anthropic:claude-sonnet-4-5", "google-gla:gemini-2.5-pro"; the provider's
    # API key (OPENAI_API_KEY, ANTHROPIC_API_KEY, ...) must be in the environment.
    agent_model: str = "openai:gpt-5.4-mini"
    # Real-DFT engine (Milestone 6).
    artifacts_dir: str = "./gibbs_data"
    pw_command: str = "pw.x"
    pseudo_dir: str = "infra/pseudopotentials"
    omp_num_threads: int = 4
    # Durable execution (Milestone 7). executor: "local" | "temporal".
    executor: str = "local"
    temporal_address: str = "localhost:7233"
    temporal_task_queue: str = "gibbs-calculations"
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

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: Any) -> Any:
        if isinstance(value, str):
            text = value.strip()
            if text.startswith("["):
                return json.loads(text)
            return [origin.strip() for origin in text.split(",") if origin.strip()]
        return value

    @field_validator("database_url")
    @classmethod
    def _normalize_database_url(cls, value: str) -> str:
        return normalize_database_url(value)

    @field_validator("pseudo_dir")
    @classmethod
    def _anchor_pseudo_dir(cls, value: str) -> str:
        """A relative pseudo_dir is relative to the repo root, whatever the cwd
        (the API is started from the root, apps/api, or a container)."""
        if os.path.isabs(value) or os.path.isdir(value):
            return value
        candidate = os.path.join(REPO_ROOT, value)
        return candidate if os.path.isdir(candidate) else value

    model_config = SettingsConfigDict(
        env_prefix="ALLOYLAB_",
        # Works from the repo root (`uv run ...`) and from apps/api (`pnpm --filter @gibbs/api dev`).
        env_file=ENV_FILES,
        extra="ignore",
    )


def load_env_files() -> None:
    """Export the env files' variables into the process environment.

    pydantic-settings only maps env-file lines onto Settings fields; provider
    keys such as OPENAI_API_KEY / ANTHROPIC_API_KEY are read by Pydantic AI
    from os.environ, so they must be exported as well. Existing environment
    variables are never overridden (deployed platforms inject real ones).
    """
    from dotenv import load_dotenv

    for path in ENV_FILES:
        if os.path.isfile(path):
            load_dotenv(path, override=False)


@lru_cache
def get_settings() -> Settings:
    load_env_files()
    return Settings()
