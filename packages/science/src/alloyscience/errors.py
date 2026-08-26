class SimulationFailure(RuntimeError):
    """A simulated experiment failure with an explicit category."""

    def __init__(self, category: str, message: str, metadata: dict | None = None):
        super().__init__(message)
        self.category = category
        self.metadata = metadata or {}
