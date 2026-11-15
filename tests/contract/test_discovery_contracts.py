import json
from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient
from click.testing import CliRunner

from src.api import app
from src.security.jwt import create_access_token
from src.cli.main import cli
from src.domains.discovery.models.contract.discovery import (
    WorkspaceKnowledgeContract,
    ResourceKnowledge,
    AttributeKnowledge,
)

client = TestClient(app)


def test_workspace_knowledge_unauthenticated():
    response = client.get("/api/v1/discovery/workspace/proj-alpha")
    assert response.status_code == 401


def test_workspace_knowledge_member_success():
    token = create_access_token(subject="alice", username="alice", roles=["user"])
    headers = {"Authorization": f"Bearer {token}"}

    mock_contract = WorkspaceKnowledgeContract(
        project_id="proj-alpha",
        enrichment_status="completed",
        resources=[
            ResourceKnowledge(
                resource_id="patients",
                format="CSV",
                tier="BRONZE",
                record_count=100,
                attributes=[
                    AttributeKnowledge(
                        name="subject_id",
                        physical_type="VARCHAR",
                        cardinality=100,
                        null_ratio=0.0,
                        pattern="UUID",
                    )
                ],
            )
        ],
    )

    with patch("src.domains.discovery.facade.discovery.DiscoveryFacade.get_workspace_knowledge", return_value=mock_contract):
        response = client.get("/api/v1/discovery/workspace/proj-alpha", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["project_id"] == "proj-alpha"
        assert len(data["resources"]) == 1
        assert data["resources"][0]["resource_id"] == "patients"


def test_workspace_knowledge_non_member_404():
    token = create_access_token(subject="stranger", username="stranger", roles=["user"])
    headers = {"Authorization": f"Bearer {token}"}

    # When caller is not a member, get_workspace_knowledge returns None
    with patch("src.domains.discovery.facade.discovery.DiscoveryFacade.get_workspace_knowledge", return_value=None):
        response = client.get("/api/v1/discovery/workspace/proj-secret", headers=headers)
        assert response.status_code == 404
        assert "not found or access denied" in response.json()["detail"]


def test_cli_project_discover_member():
    runner = CliRunner()
    mock_contract = WorkspaceKnowledgeContract(
        project_id="clinical-trials",
        enrichment_status="completed",
        resources=[
            ResourceKnowledge(
                resource_id="vitals",
                format="CSV",
                tier="BRONZE",
                record_count=500,
                attributes=[
                    AttributeKnowledge(
                        name="patient_id",
                        physical_type="VARCHAR",
                        cardinality=500,
                        null_ratio=0.0,
                    )
                ],
            )
        ],
    )

    with patch("src.domains.discovery.facade.discovery.DiscoveryFacade.get_workspace_knowledge", return_value=mock_contract):
        # Human output
        result = runner.invoke(cli, ["project", "discover", "clinical-trials"])
        assert result.exit_code == 0
        assert "=== Knowledge Summary: clinical-trials ===" in result.output
        assert "vitals (BRONZE, CSV, 500 rows)" in result.output

        # JSON output
        result_json = runner.invoke(cli, ["project", "discover", "clinical-trials", "--json"])
        assert result_json.exit_code == 0
        parsed = json.loads(result_json.output)
        assert parsed["project_id"] == "clinical-trials"


def test_cli_project_discover_non_member_exit_1():
    runner = CliRunner()
    with patch("src.domains.discovery.facade.discovery.DiscoveryFacade.get_workspace_knowledge", return_value=None):
        result = runner.invoke(cli, ["project", "discover", "secret-proj"])
        assert result.exit_code == 1
        assert "not found or access denied" in result.output


def test_cross_project_api_validation_400():
    token = create_access_token(subject="alice", username="alice", roles=["user"])
    headers = {"Authorization": f"Bearer {token}"}

    # Calling /cross-project without value and without type must return 400
    response = client.get("/api/v1/discovery/cross-project", headers=headers)
    assert response.status_code == 400
    assert "At least one of query parameters" in response.json()["detail"]


def test_cross_project_api_success():
    token = create_access_token(subject="alice", username="alice", roles=["user"])
    headers = {"Authorization": f"Bearer {token}"}

    from src.domains.discovery.models.contract.discovery import EntityCorrelationContract, EntityMatch

    mock_res = EntityCorrelationContract(
        query="ACCT-99812",
        matches=[
            EntityMatch(
                project_id="proj-a",
                resource_id="patients",
                tier="BRONZE",
                attribute="account_num",
                entity_type="Identifier",
                value="ACCT-99812",
                match_method="exact",
                confidence=1.0,
            )
        ],
        total_projects=1,
    )

    with patch("src.domains.discovery.facade.discovery.DiscoveryFacade.find_entities", return_value=mock_res):
        response = client.get("/api/v1/discovery/cross-project?value=ACCT-99812", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total_projects"] == 1
        assert len(data["matches"]) == 1
        assert data["matches"][0]["project_id"] == "proj-a"


def test_cli_discover_entity_validation_error():
    runner = CliRunner()
    # Missing both --value and --type
    result = runner.invoke(cli, ["discover", "entity"])
    assert result.exit_code == 1
    assert "At least one of --value or --type" in result.output


def test_cli_discover_entity_success():
    runner = CliRunner()
    from src.domains.discovery.models.contract.discovery import EntityCorrelationContract, EntityMatch

    mock_res = EntityCorrelationContract(
        query="ACCT-99812",
        matches=[
            EntityMatch(
                project_id="proj-a",
                resource_id="patients",
                tier="BRONZE",
                attribute="account_num",
                entity_type="Identifier",
                value="ACCT-99812",
                match_method="exact",
                confidence=1.0,
            )
        ],
        total_projects=1,
    )

    with patch("src.domains.discovery.facade.discovery.DiscoveryFacade.find_entities", return_value=mock_res):
        result = runner.invoke(cli, ["discover", "entity", "--value", "ACCT-99812"])
        assert result.exit_code == 0
        assert "Matches Found Across 1 Project Workspaces" in result.output

        result_json = runner.invoke(cli, ["discover", "entity", "--value", "ACCT-99812", "--json"])
        assert result_json.exit_code == 0
        parsed = json.loads(result_json.output)
        assert parsed["total_projects"] == 1


def test_lineage_api_contract_unauthenticated():
    response = client.get("/api/v1/discovery/lineage/proj-a/gold_kpi")
    assert response.status_code == 401


def test_lineage_api_contract_success():
    token = create_access_token(subject="alice", username="alice", roles=["user"])
    headers = {"Authorization": f"Bearer {token}"}

    from src.domains.discovery.models.contract.discovery import LineageContract, LineageNode, LineageEdge

    mock_lineage = LineageContract(
        project_id="proj-a",
        dataset_id="gold_kpi",
        nodes=[
            LineageNode(resource_id="bronze_logs", project_id="proj-a", tier="BRONZE"),
            LineageNode(resource_id="gold_kpi", project_id="proj-a", tier="GOLD"),
        ],
        edges=[
            LineageEdge(source="bronze_logs", target="gold_kpi", relationship="DERIVED_FROM", run_id="run-1")
        ],
        is_root=False,
    )

    with patch("src.domains.discovery.facade.discovery.DiscoveryFacade.get_lineage", return_value=mock_lineage):
        response = client.get("/api/v1/discovery/lineage/proj-a/gold_kpi", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["project_id"] == "proj-a"
        assert data["dataset_id"] == "gold_kpi"
        assert len(data["nodes"]) == 2
        assert len(data["edges"]) == 1
        assert data["is_root"] is False


def test_lineage_api_contract_not_found():
    token = create_access_token(subject="alice", username="alice", roles=["user"])
    headers = {"Authorization": f"Bearer {token}"}

    from src.domains.discovery.models.contract.discovery import LineageContract

    empty_lineage = LineageContract(
        project_id="proj-a",
        dataset_id="unknown_ds",
        nodes=[],
        edges=[],
        is_root=True,
    )

    with patch("src.domains.discovery.facade.discovery.DiscoveryFacade.get_lineage", return_value=empty_lineage):
        response = client.get("/api/v1/discovery/lineage/proj-a/unknown_ds", headers=headers)
        assert response.status_code == 404


def test_cli_discover_lineage_commands():
    runner = CliRunner()
    from src.domains.discovery.models.contract.discovery import LineageContract, LineageNode, LineageEdge

    mock_lineage = LineageContract(
        project_id="proj-a",
        dataset_id="gold_kpi",
        nodes=[
            LineageNode(resource_id="bronze_logs", project_id="proj-a", tier="BRONZE"),
            LineageNode(resource_id="gold_kpi", project_id="proj-a", tier="GOLD"),
        ],
        edges=[
            LineageEdge(source="bronze_logs", target="gold_kpi", relationship="DERIVED_FROM", run_id="run-1")
        ],
        is_root=False,
    )

    with patch("src.domains.discovery.facade.discovery.DiscoveryFacade.get_lineage", return_value=mock_lineage):
        res = runner.invoke(cli, ["discover", "lineage", "--project", "proj-a", "--dataset", "gold_kpi"])
        assert res.exit_code == 0
        assert "=== Lineage for proj-a/gold_kpi ===" in res.output
        assert "bronze_logs" in res.output

        res_json = runner.invoke(cli, ["discover", "lineage", "--project", "proj-a", "--dataset", "gold_kpi", "--json"])
        assert res_json.exit_code == 0
        parsed = json.loads(res_json.output)
        assert parsed["dataset_id"] == "gold_kpi"

