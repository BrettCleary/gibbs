"""Durable execution via Temporal (Milestone 7).

Deliberately lazy: the Temporal workflow sandbox re-imports this package when
validating workflows, and eager imports would drag in the executor -> engine
-> icet/spglib C extensions, which cannot be loaded twice per process.
"""


def __getattr__(name):
    if name == "TemporalJobExecutor":
        from .executor import TemporalJobExecutor

        return TemporalJobExecutor
    if name == "RunCalculationWorkflow":
        from .workflows import RunCalculationWorkflow

        return RunCalculationWorkflow
    raise AttributeError(name)


__all__ = ["TemporalJobExecutor", "RunCalculationWorkflow"]
