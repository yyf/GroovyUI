from __future__ import annotations


class JobCancelled(Exception):
    """Raised when a user or system requests render cancellation."""

    def __init__(self, message: str = "Render cancelled") -> None:
        super().__init__(message)
        self.message = message
