"""Core platform primitives, base classes, and exception hierarchy."""
from src.core.exceptions import (
    ArtemisError,
    ConfigurationError,
    ConnectionError,
    ServiceUnavailableError,
)

__all__ = [
    "ArtemisError",
    "ConfigurationError",
    "ConnectionError",
    "ServiceUnavailableError",
]
