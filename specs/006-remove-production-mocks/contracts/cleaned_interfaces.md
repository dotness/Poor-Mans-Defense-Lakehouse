# Contract: Cleaned Production Component Interfaces

**Feature**: `006-remove-production-mocks`  
**Date**: 2026-10-20  

This contract documents the refactored signatures of production classes. All `mock_mode` parameters, attributes, and internal mock branching have been eliminated.

---

## 1. AI Domain Components

### `DynamicAgentLoop` (`src/domains/ai/operations/dynamic_loop.py`)
```python
class DynamicAgentLoop:
    """Executes an autonomous dynamic tool loop using Gemini Function Calling."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        tools: Optional[AgentTools] = None,
        client: Optional[genai.Client] = None,
    ):
        ...
```
- **Removed**: `mock_mode` parameter, `self.mock_mode`, and the private `_run_simulated_loop` method.
- **Added**: `client: Optional[genai.Client] = None` for injecting genuine client or test double.
- **Behavior**: If `api_key` is missing or placeholder, raises `ConfigurationError`. If `_client.models.generate_content` fails, raises `ServiceUnavailableError`.

### `AgentTools` (`src/domains/ai/operations/tools.py`)
```python
class AgentTools:
    def __init__(
        self,
        analytics_service: Optional[AnalyticsService] = None,
        graph_facade: Optional[GraphFacade] = None,
        discovery_facade: Optional[DiscoveryFacade] = None,
        user: Optional[UserContextContract] = None,
    ):
        ...
```
- **Removed**: `mock_mode` parameter, `self.mock_mode`.

### `AIDomainFacade` (`src/domains/ai/facade/ai.py`)
```python
class AIDomainFacade:
    def __init__(
        self,
        service: Optional[GenAIService] = None,
        graph_facade: Optional[GraphFacade] = None,
    ):
        ...
```
- **Removed**: `mock_mode` parameter, `self.mock_mode`.

### `GenAIService` (`src/services/ai/genai_service.py`)
```python
class GenAIService:
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        memgraph_client: Optional[MemgraphClient] = None,
        cache: Optional[QueryCache] = None,
        audit_logger: Optional[AuditLogger] = None,
        client: Optional[genai.Client] = None,
    ):
        ...
```
- **Removed**: `mock_mode` parameter, `self.mock_mode`, and fallback text generation heuristics.

---

## 2. Graph & Discovery Components

### `MemgraphClient` (`src/services/graph/memgraph_client.py`)
```python
class MemgraphClient:
    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        driver: Optional[Driver] = None,
    ):
        ...
```
- **Removed**: `mock_mode` parameter, `self.mock_mode`, `self._mock_nodes`, `self._mock_edges`, and fallback Cypher execution simulator.
- **Behavior**: Raises `ConnectionError` if Bolt handshake fails; raises `ServiceUnavailableError` if live query fails.

### `KdgGraphStore` (`src/domains/discovery/operations/kdg_graph_store.py`)
```python
class KdgGraphStore:
    def __init__(self, client: Optional[MemgraphClient] = None):
        ...
```
- **Removed**: All `if self.client.mock_mode:` branches, `self._mock_workspaces`, `self._mock_resources`, `self._mock_attributes`, `self._mock_entities`, `self._mock_taxonomies`, `self._mock_entity_links`, `self._mock_lineage`.
- **Behavior**: Executes genuine Cypher queries against Memgraph exclusively.

---

## 3. Pipeline Components

### `DockerPipelineRunner` (`src/domains/pipeline/operations/docker_runner.py`)
```python
class DockerPipelineRunner:
    def __init__(
        self,
        default_image: Optional[str] = None,
        workspace_base: Optional[Path] = None,
        client: Optional[docker.DockerClient] = None,
    ):
        ...
```
- **Removed**: `mock_mode` parameter, `self.mock_mode`, and the local subprocess mock runner.
- **Behavior**: Connects to Docker daemon via `client` or `docker.from_env()`. Raises `ConnectionError` if daemon is unreachable; executes containers through the Docker engine exclusively.
