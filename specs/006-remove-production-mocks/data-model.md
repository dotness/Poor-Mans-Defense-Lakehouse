# Data Model: Decoupled Test Mocks & Domain Exceptions

**Feature**: `006-remove-production-mocks`  
**Date**: 2026-10-20  
**Status**: Completed  

---

## Conceptual Entities

### 1. Domain Exception Model (`src/core/exceptions.py`)

Represents the explicit error hierarchy raised when external services or configurations fail in production runtime.

```
ArtemisError (Base)
├── ConfigurationError (Missing API keys, invalid configuration parameters)
├── ConnectionError (Network unreachable, host/port connection refused)
└── ServiceUnavailableError (Gemini API 5xx, Docker daemon down, Memgraph query failure)
```

#### Fields & Attributes:
- `message: str`: Human-readable description of the failure condition.
- `service_name: str`: Identifier of the failing service (e.g., `'gemini'`, `'memgraph'`, `'docker'`, `'redis'`).
- `original_cause: Optional[Exception]`: The underlying low-level exception that triggered the failure, preserved for logging and diagnostics.

---

### 2. Production Service Operation Model

Represents standard production components operating without test flags.

```
+-----------------------------------------------------------+
| Production Component (e.g. DynamicAgentLoop, MemgraphClient)|
+-----------------------------------------------------------+
| - client: LiveClient                                      |
| - config: Settings                                        |
+-----------------------------------------------------------+
| + run(...) -> LiveResult                                  |
|   - Attempts real execution                               |
|   - On failure: raises ServiceUnavailableError             |
|   - Zero simulation or heuristic fallback branches        |
+-----------------------------------------------------------+
```

#### State Transitions:
1. `INITIALIZING`: Validates API keys and endpoints. If missing or malformed → raises `ConfigurationError`.
2. `CONNECTED`: Establishes live connection to remote socket or API client. If unreachable → raises `ConnectionError`.
3. `EXECUTING`: Submits live query or workload. If upstream fails or times out → raises `ServiceUnavailableError`.

---

### 3. Test Mock Double Model (`tests/fixtures/mocks/`)

Represents test-side mock classes that encapsulate the extracted simulation and in-memory storage logic for offline test execution.

```
+-----------------------------------------------------------+
| Mock Double (e.g. MockGenAIClient, MockMemgraphClient)     |
+-----------------------------------------------------------+
| - in_memory_store: Dict[str, Any]                         |
| - simulated_responses: List[Dict[str, Any]]               |
+-----------------------------------------------------------+
| + execute_mock_call(...) -> SimulatedResult                |
| + reset() -> None                                         |
+-----------------------------------------------------------+
```

#### Key Doubles:
- **`MockGenAIClient`**:
  - Encapsulates Gemini Function Calling candidate responses and multi-turn message handling.
  - Generates deterministic simulated tool outputs (moved from `_run_simulated_loop`).
- **`MockMemgraphClient`**:
  - Encapsulates in-memory node and edge dictionaries (`_mock_nodes`, `_mock_edges`).
  - Provides in-memory Cypher lookup matching for nodes, anomalies, and KDG metadata.
- **`MockDockerRunner`**:
  - Provides subprocess-based or stubbed script execution for testing pipeline containers without Docker daemon.
- **`MockQueryCache`**:
  - In-memory dictionary cache with TTL and rate limiting for AI tests.
- **`MockAuditLogger`**:
  - In-memory list of query audit records for verification in tests.
