import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock
from src.domains.project.facade.project import ProjectFacade
from src.domains.project.models.contract.project import ProjectCreateContract
from src.domains.pipeline.facade.pipeline import PipelineFacade
from src.domains.pipeline.models.contract.project_pipeline import (
    PipelineCreateContract,
    PipelineResponseContract,
    PipelineRunTriggerContract,
    PipelineRunResponseContract,
)
from src.domains.pipeline.operations.docker_runner import DockerPipelineRunner, DockerRunnerResult
from src.domains.pipeline.operations.pipeline_executor import PipelineExecutor


def test_docker_runner_enforces_custom_cpu_memory_and_detects_oom(tmp_path):
    mock_client = MagicMock()
    mock_container = MagicMock()
    mock_container.id = "container_custom_123"
    mock_container.wait.return_value = {"StatusCode": 0}
    mock_container.logs.return_value = b"Processed successfully\n"
    mock_container.attrs = {"State": {"OOMKilled": False}}
    mock_client.containers.run.return_value = mock_container

    runner = DockerPipelineRunner(
        workspace_base=tmp_path / "runs",
        client=mock_client,
    )
    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    in_dir.mkdir()
    out_dir.mkdir()

    # 1. Verify custom CPU and memory pass-through to containers.run
    res = runner.execute_script(
        script_content="print('ok')\n",
        input_dir=in_dir,
        output_dir=out_dir,
        cpu_limit=2.5,
        memory_limit="2048m",
    )
    assert res.success is True
    assert res.exit_code == 0
    assert res.oom_killed is False
    assert res.effective_cpu_limit == 2.5
    assert res.effective_memory_limit == "2048m"

    call_kwargs = mock_client.containers.run.call_args.kwargs
    assert call_kwargs["mem_limit"] == "2048m"
    assert call_kwargs["nano_cpus"] == int(2.5 * 1e9)

    # 2. Verify OOM exit code 137 detection and diagnostic message
    mock_container.wait.return_value = {"StatusCode": 137}
    mock_container.logs.return_value = b"Killed\n"
    mock_container.attrs = {"State": {"OOMKilled": True}}

    oom_res = runner.execute_script(
        script_content="x = 'a' * (1024**3)\n",
        input_dir=in_dir,
        output_dir=out_dir,
        cpu_limit=1.0,
        memory_limit="128m",
    )
    assert oom_res.success is False
    assert oom_res.exit_code == 137
    assert oom_res.oom_killed is True
    assert "Out of Memory (OOM)" in oom_res.error_message
    assert "128m" in oom_res.error_message
    assert "Out of Memory (OOM)" in oom_res.logs


def test_pipeline_executor_resource_hierarchy_and_oom_run_record(tmp_path):
    now = datetime.now(timezone.utc)
    mock_manager = MagicMock()
    mock_runner = MagicMock()
    mock_stager = MagicMock()

    # Pipeline has default_cpu_limit=1.5, default_memory_limit="1g"
    mock_manager.get_pipeline.return_value = PipelineResponseContract(
        pipeline_id="pipe-res-1",
        project_id="proj-res",
        name="res_pipeline",
        stage="BRONZE_TO_SILVER",
        docker_image="artemis-pipeline-runner:latest",
        default_cpu_limit=1.5,
        default_memory_limit="1g",
        version=1,
        created_by="admin",
        created_at=now,
        updated_at=now,
    )
    mock_manager.get_pipeline_script.return_value = "print('run')\n"
    mock_manager.create_run_record.return_value = PipelineRunResponseContract(
        run_id="run-res-1",
        project_id="proj-res",
        pipeline_id="pipe-res-1",
        status="RUNNING",
        stage="BRONZE_TO_SILVER",
        target_tier="SILVER",
        target_dataset="out_ds",
        started_at=now,
    )
    mock_stager.commit_outputs.return_value = ("s3://telemetry/projects/proj-res/silver/out_ds", 25, 4096)

    def _complete_side_effect(**kwargs):
        details = kwargs.get("details") or {}
        return PipelineRunResponseContract(
            run_id=kwargs["run_id"],
            project_id="proj-res",
            pipeline_id="pipe-res-1",
            status=kwargs["status"],
            stage="BRONZE_TO_SILVER",
            target_tier="SILVER",
            target_dataset="out_ds",
            records_processed=kwargs["records_processed"],
            duration_ms=kwargs["duration_ms"],
            exit_code=kwargs["exit_code"],
            logs=kwargs["logs"],
            effective_cpu_limit=details.get("effective_cpu_limit"),
            effective_memory_limit=details.get("effective_memory_limit"),
            requested_cpu_limit=details.get("requested_cpu_limit"),
            requested_memory_limit=details.get("requested_memory_limit"),
            resource_clamped=bool(details.get("resource_clamped", False)),
            details=details,
            started_at=now,
            completed_at=now,
        )

    mock_manager.complete_run_record.side_effect = _complete_side_effect
    executor = PipelineExecutor(
        pipeline_manager=mock_manager,
        docker_runner=mock_runner,
        dataset_stager=mock_stager,
    )

    # Case 1: Run without per-run overrides -> inherits pipeline defaults (1.5 CPU / 1g RAM)
    mock_runner.execute_script.return_value = DockerRunnerResult(
        exit_code=0,
        logs="OK",
        duration_ms=200,
        container_id="c1",
        success=True,
    )
    run1 = executor.trigger_run(
        project_id="proj-res",
        identifier="pipe-res-1",
        contract=PipelineRunTriggerContract(
            input_datasets=["in_ds"],
            target_dataset="out_ds",
            target_tier="SILVER",
        ),
    )
    assert run1.status == "SUCCESS"
    assert run1.effective_cpu_limit == 1.5
    assert run1.effective_memory_limit == "1g"
    assert run1.details["cpu_source"] == "pipeline_default"
    assert run1.details["memory_source"] == "pipeline_default"
    assert mock_runner.execute_script.call_args.kwargs["cpu_limit"] == 1.5
    assert mock_runner.execute_script.call_args.kwargs["memory_limit"] == "1g"

    # Case 2: Run with per-run overrides (3.0 CPU / 2048m RAM) -> overrides pipeline defaults
    run2 = executor.trigger_run(
        project_id="proj-res",
        identifier="pipe-res-1",
        contract=PipelineRunTriggerContract(
            input_datasets=["in_ds"],
            target_dataset="out_ds",
            target_tier="SILVER",
            cpu_limit=3.0,
            memory_limit="2048m",
        ),
    )
    assert run2.status == "SUCCESS"
    assert run2.effective_cpu_limit == 3.0
    assert run2.effective_memory_limit == "2048m"
    assert run2.requested_cpu_limit == 3.0
    assert run2.requested_memory_limit == "2048m"
    assert run2.details["cpu_source"] == "run_override"
    assert run2.details["memory_source"] == "run_override"
    assert mock_runner.execute_script.call_args.kwargs["cpu_limit"] == 3.0
    assert mock_runner.execute_script.call_args.kwargs["memory_limit"] == "2048m"

    # Case 3: Runtime OOM kill (exit code 137) -> status FAILED, exit_code 137, explicit OOM diagnostic message
    mock_runner.execute_script.return_value = DockerRunnerResult(
        exit_code=137,
        logs="Killed",
        duration_ms=450,
        container_id="c_oom",
        success=False,
        oom_killed=True,
    )
    run_oom = executor.trigger_run(
        project_id="proj-res",
        identifier="pipe-res-1",
        contract=PipelineRunTriggerContract(
            input_datasets=["in_ds"],
            target_dataset="out_ds",
            target_tier="SILVER",
            memory_limit="128m",
        ),
    )
    assert run_oom.status == "FAILED"
    assert run_oom.exit_code == 137
    assert run_oom.effective_memory_limit == "128m"
    assert run_oom.details["oom_killed"] is True
    assert "Out of Memory (OOM)" in run_oom.details["error"]
    assert "128m" in run_oom.details["error"]
    assert "Out of Memory (OOM)" in run_oom.logs


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

    # 4. Create pipeline transformation script with pipeline-level resource defaults
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
            default_cpu_limit=1.5,
            default_memory_limit="1g",
        ),
    )
    assert pipeline.default_cpu_limit == 1.5
    assert pipeline.default_memory_limit == "1g"

    # 5. Trigger Pipeline Run with custom per-run CPU & memory override
    run_res = await pipe_facade.trigger_pipeline_run(
        project_id=project_id,
        identifier=pipeline.pipeline_id,
        contract=PipelineRunTriggerContract(
            input_datasets=["raw_traffic"],
            target_dataset="clean_traffic",
            target_tier="SILVER",
            timeout_seconds=30,
            cpu_limit=2.0,
            memory_limit="1536m",
        ),
    )

    assert run_res.status == "SUCCESS"
    assert run_res.records_processed == 3
    assert run_res.target_dataset == "clean_traffic"
    assert run_res.target_tier == "SILVER"
    assert run_res.exit_code == 0
    assert run_res.effective_cpu_limit == 2.0
    assert run_res.effective_memory_limit == "1536m"
    assert run_res.resource_clamped is False

    # 6. Verify Silver dataset registered in project catalog
    datasets = await proj_facade.list_datasets(project_id=project_id, tier="SILVER")
    dataset_ids = [d.dataset_id for d in datasets]
    assert "clean_traffic" in dataset_ids

    # 7. Verify run history records the effective CPU and memory limits
    runs = await pipe_facade.list_pipeline_runs(project_id, pipeline.pipeline_id)
    assert len(runs) >= 1
    assert runs[0].status == "SUCCESS"
    assert runs[0].effective_cpu_limit == 2.0
    assert runs[0].effective_memory_limit == "1536m"

    # 8. Clean up
    await proj_facade.delete_project(project_id)
