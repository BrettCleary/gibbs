"""One place that knows how to reach Temporal.

The API process (TemporalJobExecutor) and the worker process both connect, and
they must agree on namespace and credentials or they sit on different queues and
nothing runs. Local `temporal server start-dev` needs neither TLS nor a key;
Temporal Cloud needs both plus a fully qualified "<namespace>.<account>".
"""

from __future__ import annotations

from ..config import Settings


async def connect_temporal_client(settings: Settings):
    from temporalio.client import Client

    kwargs: dict = {"namespace": settings.temporal_namespace}
    if settings.temporal_api_key:
        # An API key is only accepted over TLS, so it implies it.
        kwargs["api_key"] = settings.temporal_api_key
        kwargs["tls"] = True
    elif settings.temporal_tls:
        kwargs["tls"] = True
    return await Client.connect(settings.temporal_address, **kwargs)


def describe_target(settings: Settings) -> str:
    """Connection summary for logs — never includes the API key."""
    auth = "api-key" if settings.temporal_api_key else ("tls" if settings.temporal_tls else "insecure")
    return f"{settings.temporal_address} ns={settings.temporal_namespace} auth={auth}"
