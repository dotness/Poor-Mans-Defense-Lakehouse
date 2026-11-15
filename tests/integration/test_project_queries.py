import pytest
from src.domains.project.facade.project import ProjectFacade
from src.domains.project.models.contract.project import ProjectCreateContract
from src.domains.analytics.operations.project_query import ProjectQueryExecutor


@pytest.mark.asyncio
async def test_project_scoped_duckdb_queries():
    proj_facade = ProjectFacade()
    project_id = "test-proj-queries"

    # Cleanup
    try:
        await proj_facade.delete_project(project_id)
    except Exception:
        pass

    # 1. Create Project
    await proj_facade.create_project(
        ProjectCreateContract(project_id=project_id, name="Query Test Project")
    )

    # 2. Ingest sample data to Bronze
    csv_bytes = (
        b"device_id,cpu_usage,status\n"
        b"srv-alpha,88.2,OK\n"
        b"srv-beta,92.5,ALERT\n"
        b"srv-gamma,41.0,OK\n"
    )
    await proj_facade.ingest_tabular(
        project_id=project_id,
        dataset_name="system_stats",
        data_bytes=csv_bytes,
        filename="stats.csv",
        tier="BRONZE",
    )

    executor = ProjectQueryExecutor()

    # 3. Successful query scoped to project partition
    sql = f"SELECT device_id, cpu_usage FROM read_parquet('s3://telemetry/projects/{project_id}/bronze/**/*.parquet') ORDER BY cpu_usage DESC"
    res = executor.execute_scoped_query(project_id=project_id, sql=sql)

    assert res["empty"] is False
    assert res["row_count"] == 3
    assert res["columns"] == ["device_id", "cpu_usage"]
    assert res["rows"][0][0] == "srv-beta"

    # 4. Guardrail violation: attempt cross-project data bleed
    illegal_sql = "SELECT * FROM read_parquet('s3://telemetry/projects/unauthorized-tenant/bronze/**/*.parquet')"
    with pytest.raises(ValueError) as excinfo:
        executor.execute_scoped_query(project_id=project_id, sql=illegal_sql)
    assert "Access Denied" in str(excinfo.value)

    # 5. Empty project query handling
    empty_sql = "SELECT * FROM read_parquet('s3://telemetry/projects/test-proj-queries/gold/**/*.parquet')"
    empty_res = executor.execute_scoped_query(project_id=project_id, sql=empty_sql)
    assert empty_res["empty"] is True
    assert empty_res["row_count"] == 0

    # Clean up
    await proj_facade.delete_project(project_id)
