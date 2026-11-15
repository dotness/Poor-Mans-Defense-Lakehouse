import pytest
from src.domains.ai.operations.tools import AgentTools
from src.domains.graph.facade.graph import GraphFacade


@pytest.mark.asyncio
async def test_agent_tools_schema_info(mock_memgraph_client):
    tools = AgentTools(graph_facade=GraphFacade(client=mock_memgraph_client))
    res = await tools.get_schema_info("all")
    assert res["status"] == "SUCCESS"
    assert "duckdb_telemetry" in res["schemas"]
    assert "memgraph_knowledge_graph" in res["schemas"]


@pytest.mark.asyncio
async def test_agent_tools_query_graph_mock(mock_memgraph_client):
    tools = AgentTools(graph_facade=GraphFacade(client=mock_memgraph_client))
    cypher = "MATCH (a:ANOMALY) RETURN a LIMIT 5"
    res = await tools.query_graph(cypher)
    assert res["status"] == "SUCCESS"
    assert res["database"] == "memgraph"
    assert res["record_count"] > 0
    assert "duration_ms" in res


@pytest.mark.asyncio
async def test_agent_tools_query_analytics_read_only_rejection(mock_memgraph_client):
    tools = AgentTools(graph_facade=GraphFacade(client=mock_memgraph_client))
    bad_sql = "DROP TABLE telemetry"
    res = await tools.query_analytics(bad_sql)
    assert res["status"] == "ERROR"
    assert "Unauthorized SQL query" in res["error"] or "Mutating SQL keyword" in res["error"]


@pytest.mark.asyncio
async def test_agent_tools_query_graph_read_only_rejection(mock_memgraph_client):
    tools = AgentTools(graph_facade=GraphFacade(client=mock_memgraph_client))
    bad_cypher = "CREATE (n:Entity {id: '1'})"
    res = await tools.query_graph(bad_cypher)
    assert res["status"] == "ERROR"
    assert "Mutating Cypher keyword" in res["error"]
