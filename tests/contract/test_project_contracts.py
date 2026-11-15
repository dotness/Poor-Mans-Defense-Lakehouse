import pytest
from datetime import datetime, timezone
from pydantic import ValidationError
from src.domains.project.models.contract.project import (
    ProjectCreateContract,
    ProjectResponseContract,
    ProjectDatasetContract,
    TabularIngestResponseContract,
    GraphNodeContract,
    GraphEdgeContract,
    GraphIngestRequestContract,
    GraphIngestResponseContract,
)


def test_project_create_contract_valid():
    contract = ProjectCreateContract(
        project_id="cyber-defense-01",
        name="Cyber Defense Project",
        description="Perimeter monitoring",
    )
    assert contract.project_id == "cyber-defense-01"
    assert contract.name == "Cyber Defense Project"


def test_project_create_contract_invalid_slug():
    with pytest.raises(ValidationError):
        ProjectCreateContract(
            project_id="Invalid Slug With Spaces!",
            name="Valid Name",
        )


def test_project_response_contract_fields():
    now = datetime.now(timezone.utc)
    res = ProjectResponseContract(
        project_id="alpha-test",
        name="Alpha",
        description="Alpha desc",
        status="ACTIVE",
        created_at=now,
        updated_at=now,
    )
    assert res.project_id == "alpha-test"
    assert res.status == "ACTIVE"


def test_tabular_ingest_response_contract():
    res = TabularIngestResponseContract(
        status="SUCCESS",
        project_id="alpha-test",
        tier="BRONZE",
        dataset_name="syslog",
        records_ingested=120,
        storage_uri="s3://telemetry/projects/alpha-test/bronze/syslog/file.parquet",
    )
    assert res.records_ingested == 120
    assert res.tier == "BRONZE"


def test_graph_ingest_contracts():
    req = GraphIngestRequestContract(
        nodes=[GraphNodeContract(name="192.168.1.1", label="IP_ADDRESS", properties={"asn": "AS1234"})],
        edges=[GraphEdgeContract(source="attacker.com", target="192.168.1.1", relationship="RESOLVES_TO")],
    )
    assert len(req.nodes) == 1
    assert req.nodes[0].name == "192.168.1.1"
    assert len(req.edges) == 1
    assert req.edges[0].relationship == "RESOLVES_TO"
