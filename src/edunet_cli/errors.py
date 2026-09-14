"""Errors safe to show without exposing URLs, credentials or response bodies."""


class PortalError(Exception):
    """An expected operational error with a public message."""

    def __init__(self, message: str, *, code: int = 1) -> None:
        super().__init__(message)
        self.code = code
