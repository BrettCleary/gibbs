from .executor import JobExecutor


def create_executor(settings):
    """Executor selected by settings: local asyncio (default) or Temporal."""
    if settings.executor == "temporal":
        from ..temporal import TemporalJobExecutor

        return TemporalJobExecutor(settings)
    return JobExecutor(max_concurrent=settings.max_concurrent_jobs)


__all__ = ["JobExecutor", "create_executor"]
