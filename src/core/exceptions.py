from typing import Optional


class ArtemisError(Exception):
    """Base exception for all Poor Man's Defense Lakehouse operational errors."""

    def __init__(self, message: str, original_cause: Optional[Exception] = None):
        super().__init__(message)
        self.message = message
        self.original_cause = original_cause


class ConfigurationError(ArtemisError):
    """Raised when required credentials, endpoints, or settings are missing or malformed."""

    def __init__(self, message: str, key: Optional[str] = None):
        super().__init__(message)
        self.key = key


class ConnectionError(ArtemisError):
    """Raised when an external daemon or host is unreachable at initialization or execution."""

    def __init__(
        self,
        message: str,
        host: Optional[str] = None,
        port: Optional[int] = None,
        original_cause: Optional[Exception] = None,
    ):
        super().__init__(message, original_cause=original_cause)
        self.host = host
        self.port = port


class ServiceUnavailableError(ArtemisError):
    """Raised when an external service (Gemini API, Memgraph, Docker) fails during live operation."""

    def __init__(
        self,
        message: str,
        service: Optional[str] = None,
        original_cause: Optional[Exception] = None,
    ):
        super().__init__(message, original_cause=original_cause)
        self.service = service
