import pytest
from src.services.graph.memgraph_client import MemgraphClient
from src.domains.discovery.operations.kdg_graph_store import KDGGraphStore


@pytest.fixture
def graph_store(mock_kdg_store):
    return mock_kdg_store


def test_merge_workspace_and_resource(graph_store):
    ws = graph_store.merge_workspace(project_id="proj-a", name="Project Alpha", owner="alice")
    assert ws["project_id"] == "proj-a"

    res = graph_store.merge_data_resource(
        project_id="proj-a",
        resource_id="patients",
        format="PARQUET",
        tier="BRONZE",
        record_count=100,
        location_uri="s3://telemetry/projects/proj-a/bronze/patients/",
    )
    assert res["resource_id"] == "patients"
    assert res["tier"] == "BRONZE"


def test_attribute_and_taxonomy_mapping(graph_store):
    graph_store.merge_workspace("proj-a", "Project Alpha")
    graph_store.merge_data_resource("proj-a", "patients")

    attr = graph_store.merge_data_attribute(
        project_id="proj-a",
        resource_id="patients",
        name="patient_id",
        physical_type="VARCHAR",
        pattern="uuid",
    )
    assert attr["name"] == "patient_id"

    graph_store.merge_semantic_taxonomy(
        concept_id="tax-001",
        name="Taxonomy:UniqueIdentifier",
        description="Standard identifier concept",
    )
    graph_store.map_attribute_to_taxonomy(
        project_id="proj-a",
        resource_id="patients",
        attribute_name="patient_id",
        taxonomy_name="Taxonomy:UniqueIdentifier",
        confidence=0.92,
        low_confidence=False,
    )

    summary = graph_store.get_workspace_knowledge("proj-a", member_projects=["proj-a"])
    assert summary is not None
    assert len(summary.resources) == 1
    assert summary.resources[0].attributes[0].taxonomy == "Taxonomy:UniqueIdentifier"
    assert summary.resources[0].attributes[0].confidence == 0.92


def test_workspace_knowledge_membership_confinement(graph_store):
    graph_store.merge_workspace("proj-secret", "Secret Project")
    graph_store.merge_data_resource("proj-secret", "sensitive_data")

    # Non-member access returns None
    result = graph_store.get_workspace_knowledge("proj-secret", member_projects=["proj-other"])
    assert result is None

    # Member access returns summary
    result_member = graph_store.get_workspace_knowledge("proj-secret", member_projects=["proj-secret"])
    assert result_member is not None
    assert len(result_member.resources) == 1


def test_find_cross_project_entities_member_scoping(graph_store):
    # Proj A has ACCT-99812
    graph_store.merge_workspace("proj-a", "Project Alpha")
    graph_store.merge_data_resource("proj-a", "patients", tier="BRONZE")
    graph_store.merge_generic_entity(
        project_id="proj-a",
        resource_id="patients",
        attribute_name="subject_id",
        entity_type="Identifier",
        value="ACCT-99812",
        normalized_value="acct-99812",
    )

    # Proj B has ACCT-99812
    graph_store.merge_workspace("proj-b", "Project Beta")
    graph_store.merge_data_resource("proj-b", "accounts", tier="GOLD")
    graph_store.merge_generic_entity(
        project_id="proj-b",
        resource_id="accounts",
        attribute_name="account_num",
        entity_type="Identifier",
        value="ACCT-99812",
        normalized_value="acct-99812",
    )

    # User who is member of BOTH proj-a and proj-b
    both_res = graph_store.find_cross_project_entities(
        value="ACCT-99812",
        member_projects=["proj-a", "proj-b"],
    )
    assert len(both_res.matches) == 2
    assert both_res.total_projects == 2

    # User who is ONLY member of proj-a sees ZERO matches and ZERO counts from proj-b
    single_res = graph_store.find_cross_project_entities(
        value="ACCT-99812",
        member_projects=["proj-a"],
    )
    assert len(single_res.matches) == 1
    assert single_res.total_projects == 1
    assert single_res.matches[0].project_id == "proj-a"

    # User with NO membership sees nothing
    no_res = graph_store.find_cross_project_entities(
        value="ACCT-99812",
        member_projects=[],
    )
    assert len(no_res.matches) == 0
    assert no_res.total_projects == 0


def test_lineage_and_pruning(graph_store):
    graph_store.merge_workspace("proj-a", "Project Alpha")
    graph_store.merge_data_resource("proj-a", "bronze_logs")
    graph_store.merge_data_resource("proj-a", "gold_kpi")

    graph_store.record_pipeline_execution(
        run_id="run-101",
        pipeline_id="pipe-01",
        project_id="proj-a",
        status="SUCCESS",
        input_datasets=["bronze_logs"],
        target_dataset="gold_kpi",
    )

    lineage = graph_store.get_lineage("proj-a", "gold_kpi", member_projects=["proj-a"])
    assert not lineage.is_root
    assert any(e.source == "bronze_logs" for e in lineage.edges)

    # Non-member gets empty lineage
    foreign_lineage = graph_store.get_lineage("proj-a", "gold_kpi", member_projects=["proj-other"])
    assert len(foreign_lineage.nodes) == 0
