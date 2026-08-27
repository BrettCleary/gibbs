"""Arize AX tracing for the Pydantic AI agents (LLM scientist + reporter).

Opt-in: enabled only when ``ARIZE_SPACE_ID`` and ``ARIZE_API_KEY`` are in the
environment; otherwise ``setup_tracing()`` is a no-op so tests and keyless dev
runs are unaffected. Optional: ``ARIZE_PROJECT_NAME`` (default ``alloylab``) and
``ARIZE_COLLECTOR_ENDPOINT`` for non-US regions (e.g.
``https://otlp.eu-west-1a.arize.com/v1``).

Call ``setup_tracing()`` once per process, before any agent runs. Pydantic AI
emits its own OpenTelemetry spans (agent run -> model request -> tool call ->
output validation); the OpenInference span processor rewrites them into the
attributes Arize expects, so no manual spans are needed.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("alloylab.tracing")

_tracer_provider = None


def tracing_enabled() -> bool:
    return bool(os.environ.get("ARIZE_SPACE_ID") and os.environ.get("ARIZE_API_KEY"))


def setup_tracing() -> bool:
    """Register the Arize tracer provider and instrument Pydantic AI. Idempotent.

    Returns True when tracing is active.
    """
    global _tracer_provider
    if _tracer_provider is not None:
        return True
    if not tracing_enabled():
        logger.info("Arize tracing disabled (ARIZE_SPACE_ID / ARIZE_API_KEY not set)")
        return False

    from arize.otel import register
    from openinference.instrumentation.pydantic_ai import OpenInferenceSpanProcessor
    from pydantic_ai import Agent

    _tracer_provider = register(
        project_name=os.environ.get("ARIZE_PROJECT_NAME", "alloylab"),
        # space_id / api_key / endpoint are read from ARIZE_* env vars by register().
        span_processors=[OpenInferenceSpanProcessor()],
        verbose=False,
    )
    Agent.instrument_all()
    logger.info("Arize tracing enabled (project=%s)", os.environ.get("ARIZE_PROJECT_NAME", "alloylab"))
    return True


def shutdown_tracing() -> None:
    """Flush pending spans; call on process exit so batched exports are not dropped."""
    global _tracer_provider
    if _tracer_provider is None:
        return
    try:
        _tracer_provider.force_flush()
        _tracer_provider.shutdown()
    finally:
        _tracer_provider = None
