import pytest
from src.core.exceptions import (
    ArtemisError,
    ConfigurationError,
    ConnectionError,
    ServiceUnavailableError,
)
from tests.fixtures.mocks import (
    MockMemgraphClient,
    MockQueryCache,
    MockAuditLogger,
    MockDockerRunner,
    MockGenAIClient,
    MockKDGGraphStore,
)


def test_exception_hierarchy():
    base = ArtemisError("Base error")
    assert isinstance(base, Exception)

    cfg = ConfigurationError("Missing key", key="api_key")
    assert isinstance(cfg, ArtemisError)
    assert cfg.key == "api_key"

    conn = ConnectionError("Connection refused", host="localhost", port=7687)
    assert isinstance(conn, ArtemisError)
    assert conn.host == "localhost"
    assert conn.port == 7687

    svc = ServiceUnavailableError("Inference failed", service="gemini")
    assert isinstance(svc, ArtemisError)
    assert svc.service == "gemini"


def test_mock_memgraph_client(mock_memgraph_client):
    node = mock_memgraph_client.add_node("PERSON", "Alice", {"role": "admin"})
    assert node["name"] == "Alice"
    assert node["role"] == "admin"

    edge = mock_memgraph_client.add_edge("Alice", "Bob", "KNOWS")
    assert edge["relationship"] == "KNOWS"

    related = mock_memgraph_client.find_related_entities("Alice")
    assert len(related) >= 1
    assert related[0]["entity"] == "Alice"


def test_mock_query_cache(mock_query_cache):
    mock_query_cache.set("test prompt", "cached answer", ttl=10)
    assert mock_query_cache.get("test prompt") == "cached answer"
    assert mock_query_cache.get("unknown prompt") is None
    assert mock_query_cache.check_rate_limit("user-1", limit=5) is True


def test_mock_audit_logger(mock_audit_logger):
    qid = mock_audit_logger.log_query(
        user_id="analyst",
        prompt="who are you?",
        response="Artemis AI",
        model_used="gemini-2.0",
        duration_ms=45,
    )
    assert qid is not None
    logs = mock_audit_logger.get_logs()
    assert len(logs) == 1
    assert logs[0]["query_id"] == qid


def test_mock_docker_runner(mock_docker_runner, tmp_path):
    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    in_dir.mkdir()
    out_dir.mkdir()

    script = "print('Hello from mock runner')"
    res = mock_docker_runner.execute_script(script, in_dir, out_dir)
    assert res.success is True
    assert "Hello from mock runner" in res.logs


def test_mock_genai_client(mock_genai_client):
    from google.genai import types

    contents = [types.Content(role="user", parts=[types.Part.from_text(text="who are you?")])]
    resp = mock_genai_client.models.generate_content("gemini-2.5", contents)
    assert resp.candidates is not None
    assert "Artemis AI" in resp.candidates[0].content.parts[0].text
