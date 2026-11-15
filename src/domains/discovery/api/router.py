import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, status, Depends, Query
from pydantic import BaseModel

try:
    from src.security.middleware import authenticate_user
    from src.domains.discovery.facade.discovery import DiscoveryFacade
    from src.domains.discovery.models.contract.discovery import (
        WorkspaceKnowledgeContract,
        EntityCorrelationContract,
        LineageContract,
        IndexJobContract,
    )
except ImportError:
    from security.middleware import authenticate_user
    from domains.discovery.facade.discovery import DiscoveryFacade
    from domains.discovery.models.contract.discovery import (
        WorkspaceKnowledgeContract,
        EntityCorrelationContract,
        LineageContract,
        IndexJobContract,
    )

logger = logging.getLogger("artemis.discovery.api")

router = APIRouter(prefix="/api/v1/discovery", tags=["Knowledge Discovery"])
discovery_facade = DiscoveryFacade()


class ReindexRequest(BaseModel):
    dataset_id: Optional[str] = None


@router.get("/workspace/{project_id}", response_model=WorkspaceKnowledgeContract)
async def get_workspace_knowledge(
    project_id: str,
    user: Optional[dict] = Depends(authenticate_user),
):
    """Retrieves full knowledge discovery summary for a project workspace."""
    summary = await discovery_facade.get_workspace_knowledge(project_id, user=user)
    if summary is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project workspace '{project_id}' not found or access denied.",
        )
    return summary


@router.get("/cross-project", response_model=EntityCorrelationContract)
async def find_cross_project_entities(
    value: Optional[str] = Query(default=None, description="Entity value to search"),
    type: Optional[str] = Query(default=None, description="Entity classification type"),
    fuzzy: bool = Query(default=False, description="Enable typo-tolerant fuzzy matching"),
    user: Optional[dict] = Depends(authenticate_user),
):
    """Searches for entity matches across member projects."""
    if not value and not type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one of query parameters 'value' or 'type' must be provided.",
        )
    return await discovery_facade.find_entities(
        value=value,
        entity_type=type,
        fuzzy=fuzzy,
        user=user,
    )


@router.get("/lineage/{project_id}/{dataset_id}", response_model=LineageContract)
async def get_data_lineage(
    project_id: str,
    dataset_id: str,
    depth: int = Query(default=10, ge=1, le=20, description="Max traversal depth"),
    user: Optional[dict] = Depends(authenticate_user),
):
    """Traces data provenance and pipeline execution history."""
    lineage = await discovery_facade.get_lineage(
        project_id=project_id,
        dataset_id=dataset_id,
        depth=depth,
        user=user,
    )
    if not lineage.nodes:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource '{dataset_id}' in project '{project_id}' not found or access denied.",
        )
    return lineage


@router.post("/reindex/{project_id}", response_model=IndexJobContract, status_code=status.HTTP_202_ACCEPTED)
async def trigger_reindex(
    project_id: str,
    payload: Optional[ReindexRequest] = None,
    user: Optional[dict] = Depends(authenticate_user),
):
    """Triggers re-indexing of a project or dataset. Requires project owner or admin."""
    dataset_id = payload.dataset_id if payload else None
    try:
        return await discovery_facade.reindex(project_id, dataset_id=dataset_id, user=user)
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except Exception as e:
        logger.error(f"Error triggering reindex for {project_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to schedule reindex.")


@router.get("/jobs/{project_id}", response_model=List[IndexJobContract])
async def list_index_jobs(
    project_id: str,
    status: Optional[str] = Query(default=None, description="Filter by status: pending, running, completed, failed"),
    user: Optional[dict] = Depends(authenticate_user),
):
    """Lists indexing jobs for a project workspace."""
    return await discovery_facade.list_jobs(project_id=project_id, status=status, user=user)
