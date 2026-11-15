import os
import pytest
from src.domains.discovery.operations.structural_indexer import StructuralIndexer
from src.domains.discovery.operations.kdg_graph_store import KDGGraphStore
from src.services.graph.memgraph_client import MemgraphClient


@pytest.fixture
def mock_graph_store(mock_kdg_store):
    return mock_kdg_store


@pytest.fixture
def structural_indexer(mock_graph_store):
    return StructuralIndexer(graph_store=mock_graph_store)


def test_index_tabular_csv(structural_indexer, mock_graph_store):
    fixture_path = "tests/fixtures/discovery/patients.csv"
    assert os.path.exists(fixture_path)

    result = structural_indexer.index_resource(
        project_id="test-proj",
        resource_id="patients",
        file_path=fixture_path,
        format="CSV",
        tier="BRONZE",
    )

    assert result["status"] == "SUCCESS"
    assert result["resource_id"] == "patients"
    assert result["record_count"] >= 3

    # Check that DataResource and DataAttributes were merged into graph
    knowledge = mock_graph_store.get_workspace_knowledge("test-proj", member_projects=["test-proj"])
    assert knowledge is not None
    assert len(knowledge.resources) == 1
    res = knowledge.resources[0]
    assert res.resource_id == "patients"
    assert res.tier == "BRONZE"
    assert len(res.attributes) > 0

    attr_names = [a.name for a in res.attributes]
    assert "subject_id" in attr_names
    assert "contact_email" in attr_names


def test_index_text_document(structural_indexer, mock_graph_store):
    fixture_path = "tests/fixtures/discovery/sample_clinical_note.txt"
    assert os.path.exists(fixture_path)

    result = structural_indexer.index_resource(
        project_id="test-proj",
        resource_id="clinical_note_1",
        file_path=fixture_path,
        format="TEXT",
        tier="RAW",
    )

    assert result["status"] == "SUCCESS"
    knowledge = mock_graph_store.get_workspace_knowledge("test-proj", member_projects=["test-proj"])
    res = next(r for r in knowledge.resources if r.resource_id == "clinical_note_1")
    assert res.format == "TEXT"
    assert res.record_count > 0


def test_index_json_flattening(structural_indexer, mock_graph_store, tmp_path):
    json_file = tmp_path / "nested.json"
    json_file.write_text('{"user": {"id": "123e4567-e89b-12d3-a456-426614174000", "profile": {"age": 30, "city": "Paris"}}}')

    result = structural_indexer.index_resource(
        project_id="test-proj",
        resource_id="nested_json",
        file_path=str(json_file),
        format="JSON",
        tier="SILVER",
    )

    assert result["status"] == "SUCCESS"
    knowledge = mock_graph_store.get_workspace_knowledge("test-proj", member_projects=["test-proj"])
    res = next(r for r in knowledge.resources if r.resource_id == "nested_json")
    attr_names = [a.name for a in res.attributes]
    assert "user.profile.city" in attr_names or "user.id" in attr_names


def test_corrupt_file_handling(structural_indexer):
    # Corrupt or non-existent file should return error status without crashing
    result = structural_indexer.index_resource(
        project_id="test-proj",
        resource_id="corrupt_res",
        file_path="/tmp/nonexistent_file_xyz_123.csv",
        format="CSV",
        tier="BRONZE",
    )

    assert result["status"] == "FAILED"
    assert "error" in result
