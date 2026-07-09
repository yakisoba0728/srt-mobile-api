class SrtApiError(Exception):
    """Base error for SRT client failures."""


class SrtTransportError(SrtApiError):
    """HTTP transport failed before an app-level response was parsed."""


class SrtProtocolError(SrtApiError):
    """The server response did not match the documented protocol."""


class SrtAuthError(SrtApiError):
    """Login or session authentication failed."""


class SrtAppError(SrtApiError):
    """The server returned an app-level failure response."""

    def __init__(self, code: str | None, message: str | None, *, raw: object | None = None) -> None:
        self.code = code
        self.message = message
        self.raw = raw
        super().__init__(f"{code or 'UNKNOWN'}: {message or ''}".strip())


class SrtNetFunnelError(SrtApiError):
    """NetFunnel token parsing or acquisition failed."""
