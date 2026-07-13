from .redaction import redact_text, redact_url


class SrtApiError(Exception):
    """Base error for SRT client failures."""

    def __init__(self, message: str = "SRT API request failed") -> None:
        super().__init__(redact_url(message))


class SrtTransportError(SrtApiError):
    """HTTP transport failed before an app-level response was parsed."""


class SrtProtocolError(SrtApiError):
    """The server response did not match the documented protocol."""

    def __init__(
        self,
        message: str = "SRT protocol response was invalid",
        *,
        raw: object | None = None,
    ) -> None:
        self.raw = raw
        super().__init__(message)


class SrtAuthError(SrtApiError):
    """Login or session authentication failed."""

    def __init__(self, message: str = "SRT authentication failed") -> None:
        self.message = redact_url(message)
        super().__init__(self.message)


class SrtSessionExpiredError(SrtAuthError):
    """The server returned a login redirect or login form for an authenticated request."""

    def __init__(self, message: str = "SRT session expired", *, raw: object | None = None) -> None:
        self.raw = raw
        super().__init__(message)


class SrtAppError(SrtApiError):
    """The server returned an app-level failure response."""

    def __init__(self, code: str | None, message: str | None, *, raw: object | None = None) -> None:
        self.code = code
        self.message = redact_url(message or "")
        self.raw = raw
        safe_code = redact_url(str(code or "UNKNOWN"))
        super().__init__(f"{safe_code}: {self.message}".strip())


class SrtNetFunnelError(SrtApiError):
    """NetFunnel token parsing or acquisition failed."""

    def __init__(
        self,
        code: str | None = None,
        message: str | None = None,
        *,
        raw: object | None = None,
    ) -> None:
        self.code = code
        self.message = redact_url(message or "NetFunnel request failed")
        self.raw = raw
        safe_code = redact_url(str(code or "NETFUNNEL"))
        super().__init__(f"{safe_code}: {self.message}")
