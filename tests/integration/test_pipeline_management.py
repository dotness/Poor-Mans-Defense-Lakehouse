import pytest
from src.domains.project.facade.project import ProjectFacade
from src.domains.project.models.contract.project import ProjectCreateContract
from src.domains.pipeline.facade.pipeline import PipelineFacade
from src.domains.pipeline.models.contract.project_pipeline import (
    PipelineCreateContract,
    PipelineUpdateContract,
)


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

    # 3. Create valid pipeline
    valid_script = "import sys\nprint('Running valid script')\n"
    created = await pipe_facade.create_project_pipeline(
        project_id=project_id,
        contract=PipelineCreateContract(
            name="cleanse_syslog",
            description="Cleanses raw syslog",
            stage="BRONZE_TO_SILVER",
            script_content=valid_script,
        ),
    )
    assert created.name == "cleanse_syslog"
    assert created.version == 1
    assert created.project_id == project_id

    # 4. Get pipeline by name or ID
    fetched = await pipe_facade.get_project_pipeline(project_id, "cleanse_syslog")
    assert fetched is not None
    assert fetched.pipeline_id == created.pipeline_id

    # 5. Update pipeline script -> version should increment to 2
    updated_script = "import sys\nprint('Version 2 script')\n"
    updated = await pipe_facade.update_project_pipeline(
        project_id,
        created.pipeline_id,
        PipelineUpdateContract(script_content=updated_script),
    )
    assert updated.version == 2

    # 6. List pipelines
    pipelines = await pipe_facade.list_project_pipelines(project_id)
    assert len(pipelines) == 1
    assert pipelines[0].name == "cleanse_syslog"

    # 7. Delete pipeline
    deleted = await pipe_facade.delete_project_pipeline(project_id, created.pipeline_id)
    assert deleted is True

    # 8. Clean up project
    await proj_facade.delete_project(project_id)
