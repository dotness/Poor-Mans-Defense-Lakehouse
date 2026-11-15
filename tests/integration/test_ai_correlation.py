import pytest
from src.services.graph.memgraph_client import MemgraphClient
from src.services.graph.osint_importer import OsintImporter
from src.services.ai.cache import QueryCache
from src.services.ai.audit_logger import AuditLogger
from src.services.ai.genai_service import GenAIService


@pytest.fixture
def memgraph_fixture(mock_memgraph_client):
    client = mock_memgraph_client
    # Seed sample graph
    client.add_node("IP_ADDRESS", "198.51.100.24", {"asn": "AS64496"}, confidence=0.95)
    client.add_node("DOMAIN_NAME", "malicious-c2.org", {}, confidence=0.90)
    client.add_node("ANOMALY", "anomaly-beacon-01", {"severity": "CRITICAL"}, confidence=1.0)

    client.add_edge("malicious-c2.org", "198.51.100.24", "RESOLVES_TO")
    client.add_edge("anomaly-beacon-01", "198.51.100.24", "ASSOCIATED_WITH")
    return client


def test_memgraph_entity_correlation(memgraph_fixture):
    client = memgraph_fixture
    results = client.find_related_entities("198.51.100.24")
    assert len(results) > 0
    # Verify entity or edge connections
    found = [r.get("entity") or r.get("connected_entity") for r in results]
    assert any("198.51.100.24" in str(f) for f in found)


def test_osint_importer_to_memgraph(mock_memgraph_client):
    client = mock_memgraph_client
    importer = OsintImporter(client=client)

    json_export = """[
        {"type": "IP_ADDRESS", "data": "203.0.113.10", "source": "threat-domain.net", "confidence": 0.85},
        {"type": "DOMAIN_NAME", "data": "threat-domain.net", "source": "TARGET", "confidence": 0.95}
    ]"""

    nodes, edges = importer.parse_spiderfoot_json(json_export)
    assert len(nodes) == 2
    assert len(edges) == 1

    summary = importer.import_to_memgraph(nodes, edges)
    assert summary["nodes_imported"] == 2
    assert summary["edges_imported"] == 1


def test_genai_rag_flow_and_caching(memgraph_fixture, mock_query_cache, mock_audit_logger, mock_genai_client):
    cache = mock_query_cache
    audit = mock_audit_logger
    service = GenAIService(
        memgraph_client=memgraph_fixture,
        cache=cache,
        audit_logger=audit,
        client=mock_genai_client,
    )

    prompt = "What are the common IP addresses associated with recent anomalies?"

    # 1. First execution (uncached)
    res1 = service.ask(prompt, user_id="analyst_test")
    assert res1["cached"] is False
    assert "198.51.100.24" in res1["response"] or len(res1["context"]) > 0
    assert res1["query_id"] is not None

    # 2. Second execution (cached)
    res2 = service.ask(prompt, user_id="analyst_test")
    assert res2["cached"] is True
    assert res2["response"] == res1["response"]

    # 3. Verify audit log
    logs = audit.get_recent_logs(5)
    assert len(logs) >= 2
    assert logs[0]["prompt"] == prompt


def test_genai_rate_limiter(mock_query_cache, mock_audit_logger, mock_memgraph_client, mock_genai_client):
    cache = mock_query_cache
    service = GenAIService(
        memgraph_client=mock_memgraph_client,
        cache=cache,
        audit_logger=mock_audit_logger,
        client=mock_genai_client,
    )

    user = "rate_limited_analyst"
    # Allow up to 3 requests in short window
    for _ in range(3):
        assert cache.check_rate_limit(user_id=user, limit=3, window_seconds=10) is True

    # 4th request must be rejected
    assert cache.check_rate_limit(user_id=user, limit=3, window_seconds=10) is False
