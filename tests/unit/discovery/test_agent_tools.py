from unittest.mock import patch, MagicMock
import pytest
from src.domains.ai.operations.tools import AgentTools
from src.domains.discovery.models.contract.discovery import (
    WorkspaceKnowledgeContract,
    EntityCorrelationContract,
    LineageContract,
    LineageNode,
    EntityMatch,
)


from src.domains.graph.facade.graph import GraphFacade


@pytest.fixture
def make_tools(mock_memgraph_client):
    def _make(user=None):
        return AgentTools(graph_facade=GraphFacade(client=mock_memgraph_client), user=user)
    return _make


@pytest.mark.asyncio
async def test_discover_workspace_schema_member_scoping(make_tools):
    user = {"sub": "alice", "roles": ["user"]}
    tools = make_tools(user=user)

    mock_knowledge = WorkspaceKnowledgeContract(
        project_id="proj-a",
        resources=[],
        enrichment_status="completed",
    )

    with patch("src.domains.discovery.facade.discovery.DiscoveryFacade.get_workspace_knowledge") as mock_get_ws:
        mock_get_ws.return_value = mock_knowledge
        res = await tools.discover_workspace_schema(project_id="proj-a")

        assert res["status"] == "SUCCESS"
        assert res["workspace"]["project_id"] == "proj-a"
        # Confirm user context was forwarded, not model arguments
        mock_get_ws.assert_called_once_with("proj-a", user=user)


@pytest.mark.asyncio
async def test_discover_workspace_schema_non_member(make_tools):
    user = {"sub": "stranger", "roles": ["user"]}
    tools = make_tools(user=user)

    with patch("src.domains.discovery.facade.discovery.DiscoveryFacade.get_workspace_knowledge", return_value=None):
        res = await tools.discover_workspace_schema(project_id="secret-proj")
        assert res["status"] == "NOT_FOUND"
        assert "not found or access denied" in res["message"]


@pytest.mark.asyncio
async def test_find_cross_project_entities(make_tools):
    user = {"sub": "alice", "roles": ["user"]}
    tools = make_tools(user=user)

    mock_corr = EntityCorrelationContract(
        query="ACCT-99812",
        matches=[
            EntityMatch(
                project_id="proj-a",
                resource_id="patients",
                attribute="account_id",
                entity_type="Identifier",
                value="ACCT-99812",
            )
        ],
        total_projects=1,
    )

    with patch("src.domains.discovery.facade.discovery.DiscoveryFacade.find_entities") as mock_find:
        mock_find.return_value = mock_corr
        res = await tools.find_cross_project_entities(value="ACCT-99812", entity_type="Identifier")

        assert res["status"] == "SUCCESS"
        assert res["correlation"]["total_projects"] == 1
        assert len(res["correlation"]["matches"]) == 1
        mock_find.assert_called_once_with(value="ACCT-99812", entity_type="Identifier", fuzzy=False, user=user)


@pytest.mark.asyncio
async def test_get_data_lineage(make_tools):
    user = {"sub": "alice", "roles": ["user"]}
    tools = make_tools(user=user)

    mock_lineage = LineageContract(
        project_id="proj-a",
        dataset_id="gold_kpi",
        nodes=[LineageNode(resource_id="gold_kpi", project_id="proj-a", tier="GOLD")],
        edges=[],
        is_root=True,
    )

    with patch("src.domains.discovery.facade.discovery.DiscoveryFacade.get_lineage") as mock_lin:
        mock_lin.return_value = mock_lineage
        res = await tools.get_data_lineage(project_id="proj-a", dataset_id="gold_kpi")

        assert res["status"] == "SUCCESS"
        assert res["lineage"]["dataset_id"] == "gold_kpi"
        mock_lin.assert_called_once_with(project_id="proj-a", dataset_id="gold_kpi", depth=10, user=user)


@pytest.mark.asyncio
async def test_get_data_lineage_non_member(make_tools):
    user = {"sub": "stranger", "roles": ["user"]}
    tools = make_tools(user=user)

    empty_lineage = LineageContract(
        project_id="secret-proj",
        dataset_id="secret_data",
        nodes=[],
        edges=[],
        is_root=True,
    )

    with patch("src.domains.discovery.facade.discovery.DiscoveryFacade.get_lineage", return_value=empty_lineage):
        res = await tools.get_data_lineage(project_id="secret-proj", dataset_id="secret_data")
        assert res["status"] == "NOT_FOUND"
        assert "not found or access denied" in res["message"]



@pytest.mark.asyncio
async def test_tool_timeout(make_tools):
    import asyncio
    user = {"sub": "alice", "roles": ["user"]}
    tools = make_tools(user=user)

    async def slow_call(*args, **kwargs):
        await asyncio.sleep(10)

    with patch("src.domains.discovery.facade.discovery.DiscoveryFacade.get_workspace_knowledge", side_effect=slow_call):
        with patch("src.domains.ai.operations.tools.TOOL_TIMEOUT_SECONDS", 0.01):
            res = await tools.discover_workspace_schema(project_id="proj-a")
            assert res["status"] == "ERROR"
            assert "TimeoutError" in res.get("error", "") or res.get("duration_ms", 0) >= 10


@pytest.mark.asyncio
async def test_tool_guardrails(make_tools):
    user = {"sub": "alice", "roles": ["user"]}
    tools = make_tools(user=user)

    res = await tools.discover_workspace_schema(project_id="proj-a; DROP TABLE--")
    assert res["status"] == "ERROR"
    assert "Invalid identifier" in res["error"]


