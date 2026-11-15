import pytest
from src.domains.ai.operations.dynamic_loop import DynamicAgentLoop
from src.domains.ai.operations.tools import AgentTools
from src.domains.graph.facade.graph import GraphFacade


@pytest.mark.asyncio
async def test_dynamic_agent_loop_graph_query_selection(mock_genai_client, mock_memgraph_client):
    """Verifies that an anomaly intelligence query triggers query_graph."""
    tools = AgentTools(graph_facade=GraphFacade(client=mock_memgraph_client))
    loop = DynamicAgentLoop(tools=tools, client=mock_genai_client)

    result = await loop.run("What are the common IP addresses associated with recent anomalies?")
    assert result["model_used"] is not None
    assert "memgraph" in result["databases_consulted"]
    assert len(result["tool_calls"]) >= 1
    first_call = result["tool_calls"][0]
    assert first_call["tool_name"] == "query_graph"
    assert "cypher_query" in first_call["arguments"]
    assert "198.51.100.24" in result["response"] or "anomalies" in result["response"].lower()


@pytest.mark.asyncio
async def test_dynamic_agent_loop_analytics_query_selection(mock_genai_client, mock_memgraph_client):
    """Verifies that a telemetry aggregation query triggers query_analytics."""
    tools = AgentTools(graph_facade=GraphFacade(client=mock_memgraph_client))
    loop = DynamicAgentLoop(tools=tools, client=mock_genai_client)

    result = await loop.run("What is the average CPU load recorded by sensors?")
    assert "duckdb" in result["databases_consulted"]
    assert len(result["tool_calls"]) >= 1
    found_analytics = any(tc["tool_name"] == "query_analytics" for tc in result["tool_calls"])
    assert found_analytics


@pytest.mark.asyncio
async def test_dynamic_agent_loop_cross_database_reasoning(mock_genai_client, mock_memgraph_client):
    """Verifies that a cross-domain query triggers both DuckDB and Memgraph queries."""
    tools = AgentTools(graph_facade=GraphFacade(client=mock_memgraph_client))
    loop = DynamicAgentLoop(tools=tools, client=mock_genai_client)

    result = await loop.run("Which sensor had anomalous CPU spikes and what threat indicators are connected to it?")
    assert "duckdb" in result["databases_consulted"]
    assert "memgraph" in result["databases_consulted"]
    assert len(result["tool_calls"]) >= 2
    tool_names = [tc["tool_name"] for tc in result["tool_calls"]]
    assert "query_analytics" in tool_names
    assert "query_graph" in tool_names
