import pytest
from src.domains.auth.facade.auth import AuthFacade
from src.domains.ingestion.facade.ingestion import IngestionFacade
from src.domains.ingestion.models.contract.telemetry import TelemetryEventContract
from src.domains.analytics.facade.analytics import AnalyticsFacade
from src.domains.analytics.models.contract.query import QueryRequestContract
from src.domains.graph.facade.graph import GraphFacade
from src.domains.graph.models.contract.graph import GraphNodeContract, GraphEdgeContract
from src.domains.ai.facade.ai import AIFacade
from src.domains.ai.models.contract.ai import AIQueryRequestContract
from src.services.ai.genai_service import GenAIService
from src.domains.pipeline.facade.pipeline import PipelineFacade
from src.domains.pipeline.models.contract.pipeline import PipelineRunRequestContract


@pytest.mark.asyncio
async def test_auth_facade_authenticate():
    facade = AuthFacade()
    token_resp = await facade.authenticate("admin", "admin_password")
    assert token_resp.access_token is not None
    assert token_resp.user.username == "admin"

    verified = await facade.verify_token(token_resp.access_token)
    assert verified.username == "admin"


@pytest.mark.asyncio
async def test_ingestion_facade_ingest_event():
    facade = IngestionFacade()
    contract = TelemetryEventContract(
        device_id="test_device_facade",
        metric_name="cpu_load",
        value=55.0,
        unit="percent",
    )
    res = facade.ingest_event(contract)
    assert res.event_id == contract.event_id


@pytest.mark.asyncio
async def test_analytics_facade_query():
    facade = AnalyticsFacade()
    req = QueryRequestContract(sql="SELECT 42 as num, 'test' as label", format="json")
    res = await facade.execute_query(req)
    assert res.row_count == 1
    assert "num" in res.columns
    assert "42" in res.formatted_output


@pytest.mark.asyncio
async def test_graph_and_ai_facades_correlation(mock_memgraph_client, mock_genai_client):
    graph_facade = GraphFacade(client=mock_memgraph_client)
    await graph_facade.add_node(GraphNodeContract(name="198.51.100.99", label="IP_ADDRESS"))
    await graph_facade.add_node(GraphNodeContract(name="c2.attacker.com", label="DOMAIN_NAME"))
    await graph_facade.add_edge(GraphEdgeContract(
        source="c2.attacker.com", target="198.51.100.99", relationship="RESOLVES_TO"
    ))

    genai_service = GenAIService(
        memgraph_client=mock_memgraph_client,
        client=mock_genai_client,
    )
    ai_facade = AIFacade(graph_facade=graph_facade, service=genai_service)
    req = AIQueryRequestContract(prompt="Which IP resolves to c2.attacker.com?")
    res = await ai_facade.ask(req)
    assert res.response is not None
    assert res.cached is False


@pytest.mark.asyncio
async def test_pipeline_facade(monkeypatch):
    class MockMinioWriter:
        def write_batch(self, events):
            return f"telemetry/test_batch_{len(events)}.parquet"

    monkeypatch.setattr(
        "src.domains.ingestion.operations.flush.MinioParquetWriter",
        lambda *args, **kwargs: MockMinioWriter(),
    )
    monkeypatch.setattr(
        "src.domains.ingestion.operations.flush.record_run_in_postgres",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "src.pipelines.mqtt_to_minio.record_run_in_postgres",
        lambda *args, **kwargs: None,
    )

    facade = PipelineFacade()
    req = PipelineRunRequestContract(pipeline_name="mqtt_to_minio")
    res = await facade.run_pipeline(req)
    assert res.status == "SUCCESS"

