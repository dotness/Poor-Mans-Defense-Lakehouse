import pytest
from src.domains.project.facade.project import ProjectFacade
from src.domains.project.models.contract.project import ProjectCreateContract
from src.domains.pipeline.facade.pipeline import PipelineFacade
from src.domains.pipeline.models.contract.project_pipeline import (
    PipelineCreateContract,
    PipelineRunTriggerContract,
)


@pytest.mark.asyncio
async def test_end_to_end_containerized_pipeline_run():
    proj_facade = ProjectFacade()
    pipe_facade = PipelineFacade()
    project_id = "test-proj-docker"

    # 1. Cleanup leftover
    try:
        await proj_facade.delete_project(project_id)
    except Exception:
        pass

    # 2. Create project
    await proj_facade.create_project(
        ProjectCreateContract(project_id=project_id, name="Docker Test Project")
    )

    # 3. Ingest raw CSV data into Bronze
    raw_csv = (
        b"timestamp,device_id,cpu,memory\n"
        b"2026-10-12T12:00:00Z,sensor-1,45.0,60.0\n"
        b"2026-10-12T12:01:00Z,sensor-2,95.5,88.0\n"
        b"2026-10-12T12:02:00Z,sensor-3,30.0,40.0\n"
    )
    ingest_res = await proj_facade.ingest_tabular(
        project_id=project_id,
        dataset_name="raw_traffic",
        data_bytes=raw_csv,
        filename="traffic.csv",
        tier="BRONZE",
    )
    assert ingest_res.status == "SUCCESS"

    # 4. Create pipeline transformation script
    script = """
import glob
import pandas as pd
import pyarrow.parquet as pq

files = glob.glob('/workspace/input/*')
dfs = []
for f in files:
    if f.endswith('.parquet'):
        dfs.append(pd.read_parquet(f))
    elif f.endswith('.csv'):
        dfs.append(pd.read_csv(f))

if dfs:
    df = pd.concat(dfs, ignore_index=True)
    df['is_high_cpu'] = df['cpu'] > 90.0
    df.to_parquet('/workspace/output/clean_traffic.parquet', index=False)
    print(f"Transformed {len(df)} records")
"""

    pipeline = await pipe_facade.create_project_pipeline(
        project_id=project_id,
        contract=PipelineCreateContract(
            name="filter_traffic",
            description="Filters anomalies into silver",
            stage="BRONZE_TO_SILVER",
            script_content=script,
            docker_image="artemis-pipeline-runner:latest",
        ),
    )

    # 5. Trigger Pipeline Run
    run_res = await pipe_facade.trigger_pipeline_run(
        project_id=project_id,
        identifier=pipeline.pipeline_id,
        contract=PipelineRunTriggerContract(
            input_datasets=["raw_traffic"],
            target_dataset="clean_traffic",
            target_tier="SILVER",
            timeout_seconds=30,
        ),
    )

    assert run_res.status == "SUCCESS"
    assert run_res.records_processed == 3
    assert run_res.target_dataset == "clean_traffic"
    assert run_res.target_tier == "SILVER"
    assert run_res.exit_code == 0

    # 6. Verify Silver dataset registered in project catalog
    datasets = await proj_facade.list_datasets(project_id=project_id, tier="SILVER")
    dataset_ids = [d.dataset_id for d in datasets]
    assert "clean_traffic" in dataset_ids

    # 7. Verify run history is recorded
    runs = await pipe_facade.list_pipeline_runs(project_id, pipeline.pipeline_id)
    assert len(runs) >= 1
    assert runs[0].status == "SUCCESS"

    # 8. Clean up
    await proj_facade.delete_project(project_id)
