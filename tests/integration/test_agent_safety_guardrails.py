import pytest
from src.domains.ai.operations.tools import AgentTools
from src.domains.graph.facade.graph import GraphFacade


@pytest.mark.asyncio
async def test_agent_tools_reject_sql_mutations(mock_memgraph_client):
    """Verifies that malicious or mutating SQL queries are blocked and returned as tool errors."""
    tools = AgentTools(graph_facade=GraphFacade(client=mock_memgraph_client))
    bad_sqls = [
        "DROP TABLE telemetry",
        "DELETE FROM telemetry WHERE 1=1",
        "INSERT INTO telemetry VALUES ('x', 'y')",
        "UPDATE telemetry SET value = 0",
        "ALTER TABLE telemetry DROP COLUMN value",
    ]
    for bad_sql in bad_sqls:
        res = await tools.query_analytics(bad_sql)
        assert res["status"] == "ERROR"
        assert res["database"] == "duckdb"
        assert "error" in res
        assert "Unauthorized SQL query" in res["error"] or "Mutating SQL keyword" in res["error"]


@pytest.mark.asyncio
async def test_agent_tools_reject_cypher_mutations(mock_memgraph_client):
    """Verifies that malicious or mutating Cypher statements are blocked and returned as tool errors."""
    tools = AgentTools(graph_facade=GraphFacade(client=mock_memgraph_client))
    bad_cyphers = [
        "CREATE (n:Entity {id: 'hack'})",
        "MATCH (n:Entity) DETACH DELETE n",
        "MATCH (n:Entity) SET n.compromised = true",
        "MATCH (n:Entity) REMOVE n.secret",
        "DROP INDEX ON :Entity(id)",
    ]
    for bad_cypher in bad_cyphers:
        res = await tools.query_graph(bad_cypher)
        assert res["status"] == "ERROR"
        assert res["database"] == "memgraph"
        assert "error" in res
        assert "Mutating Cypher keyword" in res["error"]
