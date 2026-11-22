import pytest
from unittest.mock import MagicMock, patch
from src.config.settings import settings
from src.domains.project.facade.project import ProjectFacade
from src.domains.project.models.contract.project import ProjectCreateContract
from src.domains.pipeline.facade.pipeline import PipelineFacade
from src.domains.pipeline.models.contract.project_pipeline import (
    PipelineCreateContract,
    PipelineUpdateContract,
    PipelineRunTriggerContract,
)
from src.domains.pipeline.operations.pipeline_executor import PipelineExecutor


def test_hard_cap_enforcement_reject_and_clamp_modes(monkeypatch):
    mock_manager = MagicMock()
    mock_runner = MagicMock()
    mock_stager = MagicMock()

    mock_pipe = MagicMock()
    mock_pipe.pipeline_id = "pipe-cap-1"
    mock_pipe.stage = "BRONZE_TO_SILVER"
    mock_pipe.docker_image = "artemis-pipeline-runner:latest"
    mock_pipe.default_cpu_limit = None
    mock_pipe.default_memory_limit = None
    mock_manager.get_pipeline.return_value = mock_pipe
    mock_manager.get_pipeline_script.return_value = "print('ok')\n"

    executor = PipelineExecutor(
        pipeline_manager=mock_manager,
        docker_runner=mock_runner,
        dataset_stager=mock_stager,
    )

    # 1. Under default 'reject' policy, requesting CPU > 4.0 or Memory > 4g fails fast BEFORE create_run_record
    monkeypatch.setenv("DOCKER_RUNNER_RESOURCE_OVERFLOW_POLICY", "reject")
    with pytest.raises(ValueError, match="exceeds administrator hard maximum cap"):
        executor.trigger_run(
            project_id="proj-cap",
            identifier="pipe-cap-1",
            contract=PipelineRunTriggerContract(
                input_datasets=["in"],
                target_dataset="out",
                cpu_limit=8.0,
            ),
        )
    mock_manager.create_run_record.assert_not_called()
    mock_runner.execute_script.assert_not_called()

    with pytest.raises(ValueError, match="exceeds administrator hard maximum cap"):
        executor.trigger_run(
            project_id="proj-cap",
            identifier="pipe-cap-1",
            contract=PipelineRunTriggerContract(
                input_datasets=["in"],
                target_dataset="out",
                memory_limit="8g",
            ),
        )
    mock_manager.create_run_record.assert_not_called()

    # 2. Under 'clamp' policy, requesting CPU=8.0 and Memory='8g' clamps to 4.0 and '4g'
    monkeypatch.setenv("DOCKER_RUNNER_RESOURCE_OVERFLOW_POLICY", "clamp")
    mock_run_rec = MagicMock()
    mock_run_rec.run_id = "run-clamp-1"
    mock_manager.create_run_record.return_value = mock_run_rec
    mock_runner.execute_script.return_value = MagicMock(
        success=True,
        duration_ms=100,
        exit_code=0,
        logs="Clamped run OK",
        container_id="c_clamp",
    )
    mock_stager.commit_outputs.return_value = ("s3://telemetry/out", 10, 512)

    executor.trigger_run(
        project_id="proj-cap",
        identifier="pipe-cap-1",
        contract=PipelineRunTriggerContract(
            input_datasets=["in"],
            target_dataset="out",
            cpu_limit=8.0,
            memory_limit="8g",
        ),
    )
    assert mock_runner.execute_script.call_args.kwargs["cpu_limit"] == 4.0
    assert mock_runner.execute_script.call_args.kwargs["memory_limit"] == "4g"
    completed_details = mock_manager.complete_run_record.call_args.kwargs["details"]
    assert completed_details["effective_cpu_limit"] == 4.0
    assert completed_details["effective_memory_limit"] == "4g"
    assert completed_details["requested_cpu_limit"] == 8.0
    assert completed_details["requested_memory_limit"] == "8g"
    assert completed_details["resource_clamped"] is True


@pytest.mark.asyncio
async def test_pipeline_crud_and_versioning_lifecycle():
    proj_facade = ProjectFacade()
    pipe_facade = PipelineFacade()
    project_id = "test-proj-pipes"

    # Cleanup leftover
    try:
        await proj_facade.delete_project(project_id)
    except Exception:
        pass

    # 1. Create Project
    await proj_facade.create_project(
        ProjectCreateContract(project_id=project_id, name="Pipeline Project")
    )

    # 2. Reject malformed script
    with pytest.raises(ValueError) as excinfo:
        await pipe_facade.create_project_pipeline(
            project_id=project_id,
            contract=PipelineCreateContract(
                name="broken_pipeline",
                stage="BRONZE_TO_SILVER",
                script_content="def invalid syntax(): return True",
            ),
        )
    assert "Invalid script syntax" in str(excinfo.value)

    # 2b. Reject pipeline creation with default CPU or memory exceeding hard maximum cap
    with pytest.raises(ValueError, match="exceeds administrator hard maximum cap"):
        await pipe_facade.create_project_pipeline(
            project_id=project_id,
            contract=PipelineCreateContract(
                name="over_cap_pipeline",
                stage="BRONZE_TO_SILVER",
                script_content="print('ok')\n",
                default_cpu_limit=16.0,
            ),
        )

    # 3. Create valid pipeline with custom default CPU and memory
    valid_script = "import sys\nprint('Running valid script')\n"
    created = await pipe_facade.create_project_pipeline(
        project_id=project_id,
        contract=PipelineCreateContract(
            name="cleanse_syslog",
            description="Cleanses raw syslog",
            stage="BRONZE_TO_SILVER",
            script_content=valid_script,
            default_cpu_limit=1.5,
            default_memory_limit="1g",
        ),
    )
    assert created.name == "cleanse_syslog"
    assert created.version == 1
    assert created.project_id == project_id
    assert created.default_cpu_limit == 1.5
    assert created.default_memory_limit == "1g"

    # 4. Get pipeline by name or ID
    fetched = await pipe_facade.get_project_pipeline(project_id, "cleanse_syslog")
    assert fetched is not None
    assert fetched.pipeline_id == created.pipeline_id
    assert fetched.default_cpu_limit == 1.5
    assert fetched.default_memory_limit == "1g"

    # 5. Update pipeline script and default resource limits -> version should increment to 2
    updated_script = "import sys\nprint('Version 2 script')\n"
    updated = await pipe_facade.update_project_pipeline(
        project_id,
        created.pipeline_id,
        PipelineUpdateContract(
            script_content=updated_script,
            default_cpu_limit=2.5,
            default_memory_limit="2048m",
        ),
    )
    assert updated.version == 2
    assert updated.default_cpu_limit == 2.5
    assert updated.default_memory_limit == "2048m"

    # 6. List pipelines
    pipelines = await pipe_facade.list_project_pipelines(project_id)
    assert len(pipelines) == 1
    assert pipelines[0].name == "cleanse_syslog"
    assert pipelines[0].default_cpu_limit == 2.5
    assert pipelines[0].default_memory_limit == "2048m"

    # 7. Delete pipeline
    deleted = await pipe_facade.delete_project_pipeline(project_id, created.pipeline_id)
    assert deleted is True

    # 8. Clean up project
    await proj_facade.delete_project(project_id)
