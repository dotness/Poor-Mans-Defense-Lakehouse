# Contract: Test Fixtures & Mock Doubles

**Feature**: `006-remove-production-mocks`  
**Date**: 2026-10-20  
**Target Package**: `tests/fixtures/mocks/` and `tests/conftest.py`  

---

## 1. Mock Double Classes (`tests/fixtures/mocks/`)

### `MockGenAIClient` (`tests/fixtures/mocks/mock_genai.py`)
- Emulates `google.genai.Client`.
- Exposes `models.generate_content(...)`.
- Implements the multi-turn dynamic loop function calling simulation engine (previously located in `DynamicAgentLoop._run_simulated_loop`).
- Returns realistic `GenerateContentResponse` objects with `FunctionCall` parts matching the prompt intent (e.g., calling `query_analytics` or `query_graph`).

### `MockMemgraphClient` (`tests/fixtures/mocks/mock_memgraph.py`)
- Emulates `src.services.graph.memgraph_client.MemgraphClient`.
- Contains in-memory graph dictionaries: `nodes`, `edges`, and indices.
- Supports `execute_query(cypher, params)`, `find_related_entities(term)`, `save_node(...)`, `save_edge(...)`.
- Provides deterministic graph results for unit and discovery tests.

### `MockDockerRunner` (`tests/fixtures/mocks/mock_docker.py`)
- Emulates `src.domains.pipeline.operations.docker_runner.DockerPipelineRunner`.
- Executes user transformation scripts locally via subprocess in an isolated test directory or returns stubbed `DockerRunnerResult` records.
- Avoids requiring a running Docker daemon during lightweight unit tests.

### `MockQueryCache` (`tests/fixtures/mocks/mock_cache.py`)
- Emulates `src.services.ai.cache.QueryCache`.
- Provides in-memory dictionary-backed cache with time-to-live and rate-limiting support.

### `MockAuditLogger` (`tests/fixtures/mocks/mock_audit.py`)
- Emulates `src.services.ai.audit_logger.AuditLogger`.
- Appends query audit records to an in-memory list and returns generated UUID query identifiers.

---

## 2. Standard Pytest Fixtures (`tests/conftest.py`)

All test suites can inject these doubles using standard pytest fixture arguments:

```python
@pytest.fixture
def mock_genai_client() -> MockGenAIClient:
    """Provides a fresh MockGenAIClient with simulated tool calling."""
    return MockGenAIClient()

@pytest.fixture
def mock_memgraph_client() -> MockMemgraphClient:
    """Provides an isolated in-memory MockMemgraphClient."""
    return MockMemgraphClient()

@pytest.fixture
def mock_docker_runner(tmp_path) -> MockDockerRunner:
    """Provides a safe, local MockDockerRunner operating in a temp workspace."""
    return MockDockerRunner(workspace_base=tmp_path / "mock_workspace")

@pytest.fixture
def mock_query_cache() -> MockQueryCache:
    """Provides an in-memory QueryCache double."""
    return MockQueryCache()

@pytest.fixture
def mock_audit_logger() -> MockAuditLogger:
    """Provides an in-memory AuditLogger double."""
    return MockAuditLogger()
```
