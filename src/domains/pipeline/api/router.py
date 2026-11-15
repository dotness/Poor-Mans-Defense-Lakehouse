from fastapi import APIRouter, HTTPException, status
from src.domains.pipeline.facade.pipeline import PipelineFacade
from src.domains.pipeline.models.contract.pipeline import (
    PipelineRunRequestContract,
    PipelineRunResponseContract,
)

router = APIRouter(prefix="/api/v1/pipeline", tags=["Pipeline Execution"])


@router.post("/run", response_model=PipelineRunResponseContract)
async def run_pipeline(pipeline_req: PipelineRunRequestContract):
    """Executes a named batch pipeline workflow."""
    facade = PipelineFacade()
    try:
        return await facade.run_pipeline(pipeline_req)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
