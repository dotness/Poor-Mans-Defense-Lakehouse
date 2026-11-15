import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, status
from src.domains.pipeline.facade.pipeline import PipelineFacade
from src.domains.pipeline.models.contract.project_pipeline import (
    PipelineCreateContract,
    PipelineUpdateContract,
    PipelineResponseContract,
    PipelineRunTriggerContract,
    PipelineRunResponseContract,
)

logger = logging.getLogger("artemis.pipeline.api")

router = APIRouter(prefix="/api/v1/projects/{project_id}/pipelines", tags=["Project Pipelines"])
facade = PipelineFacade()


@router.post("", response_model=PipelineResponseContract, status_code=status.HTTP_201_CREATED)
async def create_pipeline(project_id: str, payload: PipelineCreateContract):
    """Creates a new shareable Pipeline entity with user transformation script."""
    try:
        return await facade.create_project_pipeline(project_id, payload)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating pipeline: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create pipeline.")


@router.get("", response_model=List[PipelineResponseContract])
async def list_pipelines(project_id: str):
    """Lists all pipelines belonging to a project."""
    return await facade.list_project_pipelines(project_id)


@router.get("/{pipeline_id}", response_model=PipelineResponseContract)
async def get_pipeline(project_id: str, pipeline_id: str):
    """Retrieves metadata for a specific pipeline in a project."""
    p = await facade.get_project_pipeline(project_id, pipeline_id)
    if not p:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Pipeline '{pipeline_id}' not found.")
    return p


@router.put("/{pipeline_id}", response_model=PipelineResponseContract)
async def update_pipeline(project_id: str, pipeline_id: str, payload: PipelineUpdateContract):
    """Updates pipeline configuration or script with atomic version increment."""
    try:
        return await facade.update_project_pipeline(project_id, pipeline_id, payload)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating pipeline: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update pipeline.")


@router.delete("/{pipeline_id}")
async def delete_pipeline(project_id: str, pipeline_id: str):
    """Deletes a pipeline from a project."""
    success = await facade.delete_project_pipeline(project_id, pipeline_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Pipeline '{pipeline_id}' not found.")
    return {"status": "DELETED", "pipeline_id": pipeline_id}


@router.post("/{pipeline_id}/run", response_model=PipelineRunResponseContract)
async def trigger_pipeline_run(project_id: str, pipeline_id: str, payload: PipelineRunTriggerContract):
    """Triggers an ephemeral Docker container execution for the pipeline."""
    try:
        return await facade.trigger_pipeline_run(project_id, pipeline_id, payload)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error triggering pipeline run: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/{pipeline_id}/runs", response_model=List[PipelineRunResponseContract])
async def list_pipeline_runs(project_id: str, pipeline_id: str):
    """Lists historical execution runs for a specific pipeline."""
    return await facade.list_pipeline_runs(project_id, pipeline_id)
