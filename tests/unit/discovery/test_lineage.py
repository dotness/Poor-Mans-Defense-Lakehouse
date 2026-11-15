import pytest
from src.domains.discovery.operations.lineage import LineageTraverser
from src.domains.discovery.operations.kdg_graph_store import KDGGraphStore
from src.services.graph.memgraph_client import MemgraphClient


@pytest.fixture
def graph_store(mock_kdg_store):
    return mock_kdg_store


def test_lineage_root_detection(graph_store):
    traverser = LineageTraverser(graph_store=graph_store)

    graph_store.merge_workspace("proj-1", "Project 1")
    graph_store.merge_data_resource("proj-1", "raw_logs")

    lineage = traverser.get_lineage("proj-1", "raw_logs", member_projects=["proj-1"])
    assert lineage.is_root is True
    assert len(lineage.edges) == 0
    assert len(lineage.nodes) >= 1
    assert lineage.nodes[0].resource_id == "raw_logs"


def test_lineage_pipeline_derivation(graph_store):
    traverser = LineageTraverser(graph_store=graph_store)

    graph_store.merge_workspace("proj-1", "Project 1")
    graph_store.merge_data_resource("proj-1", "raw_logs", tier="BRONZE")
    graph_store.merge_data_resource("proj-1", "clean_logs", tier="SILVER")
    graph_store.merge_data_resource("proj-1", "kpi_summary", tier="GOLD")

    graph_store.record_pipeline_execution(
        run_id="run-1",
        pipeline_id="pipe-clean",
        project_id="proj-1",
        status="SUCCESS",
        input_datasets=["raw_logs"],
        target_dataset="clean_logs",
    )
    graph_store.record_pipeline_execution(
        run_id="run-2",
        pipeline_id="pipe-agg",
        project_id="proj-1",
        status="SUCCESS",
        input_datasets=["clean_logs"],
        target_dataset="kpi_summary",
    )

    lineage = traverser.get_lineage("proj-1", "kpi_summary", member_projects=["proj-1"], depth=5)
    assert lineage.is_root is False
    assert len(lineage.edges) == 2
    sources = [e.source for e in lineage.edges]
    assert "clean_logs" in sources
    assert "raw_logs" in sources


def test_lineage_depth_limit(graph_store):
    traverser = LineageTraverser(graph_store=graph_store)

    graph_store.merge_workspace("proj-1", "Project 1")
    graph_store.merge_data_resource("proj-1", "n1")
    graph_store.merge_data_resource("proj-1", "n2")
    graph_store.merge_data_resource("proj-1", "n3")

    graph_store.record_pipeline_execution("r1", "p1", "proj-1", "SUCCESS", ["n1"], "n2")
    graph_store.record_pipeline_execution("r2", "p2", "proj-1", "SUCCESS", ["n2"], "n3")

    # Depth 1 should only retrieve direct parent n2, not grandparent n1
    lineage = traverser.get_lineage("proj-1", "n3", member_projects=["proj-1"], depth=1)
    edge_sources = [e.source for e in lineage.edges]
    assert "n2" in edge_sources
    assert "n1" not in edge_sources


def test_lineage_non_member_omission(graph_store):
    traverser = LineageTraverser(graph_store=graph_store)

    graph_store.merge_workspace("proj-1", "Project 1")
    graph_store.merge_workspace("proj-secret", "Secret Project")
    graph_store.merge_data_resource("proj-secret", "secret_upstream")
    graph_store.merge_data_resource("proj-1", "public_downstream")

    graph_store.record_pipeline_execution(
        run_id="run-cross",
        pipeline_id="pipe-cross",
        project_id="proj-1",
        status="SUCCESS",
        input_datasets=["secret_upstream"],
        target_dataset="public_downstream",
    )

    # When user only has access to proj-1, secret_upstream from proj-secret is omitted
    lineage = traverser.get_lineage("proj-1", "public_downstream", member_projects=["proj-1"])
    # Any edge pointing to or from non-member resource is excluded
    node_ids = [n.resource_id for n in lineage.nodes]
    assert "secret_upstream" not in node_ids
