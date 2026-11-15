import pytest
from src.core.exceptions import ConnectionError
from src.services.graph.memgraph_client import MemgraphClient
from src.domains.pipeline.operations.docker_runner import DockerPipelineRunner
from src.services.ai.cache import QueryCache
from src.services.ai.audit_logger import AuditLogger


def test_memgraph_client_unreachable_connection():
    """Validates that MemgraphClient raises ConnectionError on unreachable host/port."""
    with pytest.raises(ConnectionError):
        MemgraphClient(host="127.0.0.1", port=65530)


def test_docker_runner_unreachable_daemon():
    """Validates that DockerPipelineRunner raises ConnectionError when Docker engine is unreachable."""
    with pytest.raises(ConnectionError):
        DockerPipelineRunner(default_image="python:3.12-slim", docker_url="tcp://127.0.0.1:65531")


def test_query_cache_unreachable_redis():
    """Validates that QueryCache raises ConnectionError when Redis host is unreachable."""
    with pytest.raises(ConnectionError):
        QueryCache(host="127.0.0.1", port=65532)


def test_audit_logger_unreachable_postgres():
    """Validates that AuditLogger raises ConnectionError when PostgreSQL host is unreachable."""
    logger = AuditLogger(host="127.0.0.1", port=65533, dbname="nonexistent_db")
    with pytest.raises(ConnectionError):
        logger.log_query(
            user_id="analyst",
            prompt="test prompt",
            response="test response",
            model_used="test-model",
            duration_ms=10,
        )
