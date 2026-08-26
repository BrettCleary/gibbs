from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .agent.loop import runner_registry
from .api import benchmarks, calculations, campaigns
from .config import get_settings
from .db.base import dispose_db, init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield
    await runner_registry.shutdown()
    await dispose_db()


def create_app() -> FastAPI:
    app = FastAPI(
        title="AlloyLab API",
        description="Autonomous computational materials-science platform "
        "(V0: Ising critical-region scientist).",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(campaigns.router)
    app.include_router(calculations.router)
    app.include_router(benchmarks.router)

    @app.get("/health", tags=["meta"])
    async def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
