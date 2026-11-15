import pytest
from src.domains.project.facade.project import ProjectFacade
from src.domains.project.models.contract.project import ProjectCreateContract


@pytest.mark.asyncio
async def test_project_lifecycle_and_scoped_ingestion():
    facade = ProjectFacade()
    project_id = "test-proj-lifecycle"

    # 1. Cleanup if leftover from previous test
    try:
        await facade.delete_project(project_id)
    except Exception:
        pass

    # 2. Create Project
    created = await facade.create_project(
        ProjectCreateContract(
            project_id=project_id,
            name="Lifecycle Project",
            description="Testing end-to-end project lifecycle",
        )
    )
    assert created.project_id == project_id
    assert created.name == "Lifecycle Project"

    # 3. Retrieve Project
    retrieved = await facade.get_project(project_id)
    assert retrieved is not None
    assert retrieved.project_id == project_id

    # 4. Ingest Tabular CSV Data to Bronze
    csv_data = b"timestamp,device_id,cpu\n2026-10-12T10:00:00Z,dev-1,55.4\n2026-10-12T10:01:00Z,dev-2,72.1\n"
    tab_res = await facade.ingest_tabular(
        project_id=project_id,
        dataset_name="metrics_raw",
        data_bytes=csv_data,
        filename="metrics.csv",
        tier="BRONZE",
    )
    assert tab_res.status == "SUCCESS"
    assert tab_res.records_ingested == 2
    assert tab_res.tier == "BRONZE"
    assert "metrics_raw" in tab_res.storage_uri

    # 5. Ingest Graph Data
    nodes = [{"name": "192.168.100.5", "label": "IP_ADDRESS", "properties": {"asn": "AS999"}}]
    edges = [{"source": "bot.malware.net", "target": "192.168.100.5", "relationship": "CONNECTS_TO"}]
    graph_res = await facade.ingest_graph(
        project_id=project_id,
        nodes=nodes,
        edges=edges,
    )
    assert graph_res.status == "SUCCESS"
    assert graph_res.nodes_imported == 1
    assert graph_res.edges_imported == 1

    # 6. List Datasets in Project
    datasets = await facade.list_datasets(project_id=project_id)
    dataset_ids = [d.dataset_id for d in datasets]
    assert "metrics_raw" in dataset_ids
    assert "knowledge_graph" in dataset_ids

    # 7. Delete Project
    deleted = await facade.delete_project(project_id)
    assert deleted is True

    # 8. Verify Project is Gone
    assert await facade.get_project(project_id) is None
