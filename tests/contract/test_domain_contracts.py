import pytest
from src.domains.auth.models.contract.user import UserInfoContract, TokenResponseContract
from src.domains.ingestion.models.contract.telemetry import TelemetryEventContract, BatchFlushResultContract
from src.domains.analytics.models.contract.query import QueryRequestContract, QueryResultContract
from src.domains.graph.models.contract.graph import GraphNodeContract, GraphEdgeContract
from src.domains.ai.models.contract.ai import AIQueryRequestContract, AIQueryResponseContract
from src.domains.pipeline.models.contract.pipeline import PipelineRunRequestContract


def test_auth_contract():
    user = UserInfoContract(id="u1", username="admin", roles=["admin"])
    token_resp = TokenResponseContract(access_token="xyz", user=user)
    assert token_resp.token_type == "Bearer"
    assert token_resp.user.username == "admin"


def test_ingestion_contract():
    event = TelemetryEventContract(
        device_id="dev-1",
        metric_name="temperature",
        value=24.5,
        unit="celsius",
    )
    assert event.event_id is not None
    assert event.value == 24.5


def test_analytics_contract():
    req = QueryRequestContract(sql="SELECT 1")
    assert req.format == "table"
    res = QueryResultContract(columns=["a"], rows=[[1]], row_count=1, duration_ms=10)
    assert res.row_count == 1


def test_graph_contract():
    node = GraphNodeContract(name="198.51.100.24", label="IP_ADDRESS")
    assert node.confidence == 0.8
    edge = GraphEdgeContract(source="d1", target="198.51.100.24", relationship="RESOLVES_TO")
    assert edge.relationship == "RESOLVES_TO"


def test_ai_contract():
    req = AIQueryRequestContract(prompt="What is the anomaly?")
    assert req.user_id == "analyst"
    res = AIQueryResponseContract(
        query_id="q1",
        response="Grounded answer",
        model_used="gemini-2.5-flash",
        cached=False,
        duration_ms=45,
    )
    assert res.cached is False


def test_pipeline_contract():
    req = PipelineRunRequestContract(pipeline_name="mqtt_to_minio")
    assert req.pipeline_name == "mqtt_to_minio"
