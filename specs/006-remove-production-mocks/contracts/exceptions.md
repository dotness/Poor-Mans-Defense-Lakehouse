# Contract: Production Exception Hierarchy

**Feature**: `006-remove-production-mocks`  
**Date**: 2026-10-20  
**Target Module**: `src/core/exceptions.py` (or `src/common/exceptions.py`)  

---

## 1. Exception Classes

All custom errors inherit from a base `ArtemisError` to enable callers to catch general platform errors when needed.

```python
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
    def __init__(self, message: str, host: Optional[str] = None, port: Optional[int] = None, original_cause: Optional[Exception] = None):
        super().__init__(message, original_cause=original_cause)
        self.host = host
        self.port = port


class ServiceUnavailableError(ArtemisError):
    """Raised when an external service (Gemini API, Memgraph, Docker) fails during live operation."""
    def __init__(self, message: str, service: str, original_cause: Optional[Exception] = None):
        super().__init__(message, original_cause=original_cause)
        self.service = service
```

---

## 2. Component Error Mapping

| Component | Condition | Raised Exception |
| :--- | :--- | :--- |
| `DynamicAgentLoop` | Missing API key (empty or default placeholder) | `ConfigurationError` |
| `DynamicAgentLoop` | Gemini API unavailable or quota exceeded | `ServiceUnavailableError` |
| `GenAIService` | Missing API key | `ConfigurationError` |
| `GenAIService` | Gemini inference call fails | `ServiceUnavailableError` |
| `MemgraphClient` | Socket connect timeout / Bolt handshake failure | `ConnectionError` |
| `MemgraphClient` | Cypher query failure in live database | `ServiceUnavailableError` |
| `DockerPipelineRunner` | Docker daemon unreachable or socket error | `ConnectionError` |
| `DockerPipelineRunner` | Container execution failure or timeout | `ServiceUnavailableError` |
| `QueryCache` | Redis unreachable on startup | `ConnectionError` |
| `AuditLogger` | PostgreSQL connection failure | `ConnectionError` |
