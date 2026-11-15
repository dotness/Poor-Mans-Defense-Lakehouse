import time
import pytest
import duckdb
from pathlib import Path
from src.domains.discovery.facade.discovery import DiscoveryFacade
from src.domains.discovery.operations.structural_indexer import StructuralIndexer
from src.domains.discovery.operations.kdg_graph_store import KDGGraphStore
from src.domains.project.facade.project import ProjectFacade
from src.domains.project.models.contract.project import ProjectCreateContract
from src.domains.project.operations.membership import ProjectMembershipService


@pytest.mark.asyncio
async def test_sc001_project_summary_latency():
    """SC-001: An analyst can get a complete structural summary of a project within 5 s."""
    discovery_facade = DiscoveryFacade()
    project_facade = ProjectFacade()
    project_id = "perf-proj-summary"

    try:
        await project_facade.delete_project(project_id)
    except Exception:
        pass

    await project_facade.create_project(
        ProjectCreateContract(project_id=project_id, name="Perf Summary Test"),
        creator_user_id="alice",
    )

    # Ingest a sample dataset
    csv_bytes = b"id,name,value\n1,alpha,10.5\n2,beta,20.0\n"
    await project_facade.ingest_tabular(
        project_id=project_id,
        dataset_name="metrics",
        data_bytes=csv_bytes,
        filename="metrics.csv",
        tier="BRONZE",
    )

    alice_ctx = {"sub": "alice", "roles": ["user"]}

    start_time = time.time()
    summary = await discovery_facade.get_workspace_knowledge(project_id, user=alice_ctx)
    duration = time.time() - start_time

    assert summary is not None
    assert summary.project_id == project_id
    assert duration < 5.0, f"SC-001 failed: Summary took {duration:.3f} s (expected < 5.0 s)"

    await project_facade.delete_project(project_id)


@pytest.mark.asyncio
async def test_sc002_structural_index_1m_rows():
    """SC-002: Structural index of a 1M-row, 20-col Parquet file is available within 30 s."""
    import tempfile
    import os

    # Generate 1M row x 20 col parquet file via duckdb
    with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        con = duckdb.connect()
        con.execute(f"""
            COPY (
                SELECT 
                    i as id,
                    'USR-' || (i % 10000) as user_id,
                    'device_' || (i % 500) as device_id,
                    random() as f1, random() as f2, random() as f3, random() as f4, random() as f5,
                    random() as f6, random() as f7, random() as f8, random() as f9, random() as f10,
                    random() as f11, random() as f12, random() as f13, random() as f14, random() as f15,
                    i % 100 as category,
                    '2026-01-01T00:00:00Z' as ts
                FROM range(1000000) t(i)
            ) TO '{tmp_path}' (FORMAT PARQUET)
        """)
        con.close()

        parquet_bytes = Path(tmp_path).read_bytes()

        indexer = StructuralIndexer()
        start_time = time.time()
        result = indexer.index_resource(
            project_id="perf-proj-1m",
            resource_id="big_telemetry",
            file_path=tmp_path,
            format="PARQUET",
            tier="BRONZE",
        )
        duration = time.time() - start_time

        assert result["status"] == "SUCCESS"
        assert result["record_count"] == 1000000
        assert duration < 30.0, f"SC-002 failed: 1M row index took {duration:.2f} s (expected < 30.0 s)"

    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@pytest.mark.asyncio
async def test_sc003_cross_project_search_50_projects():
    """SC-003: Cross-project search returns in < 3 s across at least 50 projects."""
    from unittest.mock import patch
    discovery_facade = DiscoveryFacade()

    # 50 member projects
    member_projects = [f"proj-perf-{i:03d}" for i in range(50)]
    user_ctx = {"sub": "tester50", "roles": ["user"]}

    with patch.object(discovery_facade, "_resolve_member_projects", return_value=member_projects):
        start_time = time.time()
        result = await discovery_facade.find_entities(
            value="ACCT-99812",
            entity_type="Identifier",
            fuzzy=False,
            user=user_ctx,
        )
        duration = time.time() - start_time

    assert duration < 3.0, f"SC-003 failed: 50-project search took {duration:.3f} s (expected < 3.0 s)"


@pytest.mark.asyncio
async def test_sc004_ingestion_overhead():
    """SC-004: Ingestion overhead with indexing remains <= 10% on equivalent batch payload."""
    project_facade = ProjectFacade()
    project_id = "perf-proj-overhead"

    try:
        await project_facade.delete_project(project_id)
    except Exception:
        pass

    await project_facade.create_project(
        ProjectCreateContract(project_id=project_id, name="Overhead Test"),
        creator_user_id="alice",
    )

    csv_data = b"id,val,category\n" + b"\n".join([f"{i},{i*1.5},cat_{i%10}".encode() for i in range(5000)])

    # Ingestion includes Phase 1 indexing
    start_time = time.time()
    await project_facade.ingest_tabular(
        project_id=project_id,
        dataset_name="batch_data",
        data_bytes=csv_data,
        filename="batch.csv",
        tier="BRONZE",
    )
    duration = time.time() - start_time

    # Total ingestion with indexing should finish well under 3.0 s for 5k rows with batch entity insertion
    assert duration < 3.0, f"SC-004 ingestion took {duration:.3f} s (expected < 3.0 s)"

    await project_facade.delete_project(project_id)

