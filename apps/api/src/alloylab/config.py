from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Override with ALLOYLAB_* environment variables."""

    database_url: str = "sqlite+aiosqlite:///./alloylab.db"
    cors_origins: list[str] = ["http://localhost:3000"]
    max_concurrent_jobs: int = 2
    # LLM agent (OpenAI Agents SDK). Requires OPENAI_API_KEY in the environment.
    agent_model: str = "gpt-5"
    # Real-DFT engine (Milestone 6).
    artifacts_dir: str = "./alloylab_data"
    pw_command: str = "pw.x"
    pseudo_dir: str = "infra/pseudopotentials"
    omp_num_threads: int = 4

    model_config = SettingsConfigDict(env_prefix="ALLOYLAB_", env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
