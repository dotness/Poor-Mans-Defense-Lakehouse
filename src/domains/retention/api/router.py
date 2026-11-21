import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.security.middleware import authenticate_user
from src.domains.retention.facade.retention import RetentionFacade
from src.domains.retention.models.contract.retention import (
    TTLPolicyContract,
    DatasetTTLSetRequestContract,
    ProjectTTLDefaultsRequestContract,
    DatasetRetentionStateContract,
    RetentionHoldRequestContract,
    DatasetRestoreRequestContract,
    ProjectRetentionSummaryContract,
    CleanupTriggerRequestContract,
    CleanupJobRunContract,
)

logger = logging.getLogger("artemis.retention.api")

router = APIRouter(tags=["Data Retention & TTL Cleanup"])
retention_facade = RetentionFacade()


@router.put(
    "/api/v1/projects/{project_id}/datasets/{dataset_id}/ttl",
    response_model=DatasetRetentionStateContract,
)
async def set_dataset_ttl(
    project_id: str,
    dataset_id: str,
    payload: DatasetTTLSetRequestContract,
    user: Optional[dict] = Depends(authenticate_user),
):
    """Sets or updates the TTL policy for a specific project dataset (project owner or admin only)."""
    try:
        return await retention_facade.set_dataset_ttl(
            project_id=project_id,
            dataset_id=dataset_id,
            request=payload,
            user=user,
        )
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))


@router.get(
    "/api/v1/projects/{project_id}/datasets/{dataset_id}/ttl",
    response_model=DatasetRetentionStateContract,
)
async def get_dataset_ttl(
    project_id: str,
    dataset_id: str,
    tier: str = Query(default="BRONZE"),
    user: Optional[dict] = Depends(authenticate_user),
):
    """Inspects the effective TTL policy and lifecycle status of a dataset."""
    try:
        return await retention_facade.get_dataset_ttl(
            project_id=project_id,
            dataset_id=dataset_id,
            tier=tier,
            user=user,
        )
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))


@router.delete(
    "/api/v1/projects/{project_id}/datasets/{dataset_id}/ttl",
    response_model=DatasetRetentionStateContract,
)
async def clear_dataset_ttl(
    project_id: str,
    dataset_id: str,
    tier: str = Query(default="BRONZE"),
    user: Optional[dict] = Depends(authenticate_user),
):
    """Clears an explicit dataset TTL override and reverts to the tier/project default policy."""
    try:
        return await retention_facade.clear_dataset_ttl(
            project_id=project_id,
            dataset_id=dataset_id,
            tier=tier,
            user=user,
        )
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))


@router.put(
    "/api/v1/projects/{project_id}/ttl/defaults",
    response_model=TTLPolicyContract,
)
async def set_project_default_ttl(
    project_id: str,
    payload: ProjectTTLDefaultsRequestContract,
    user: Optional[dict] = Depends(authenticate_user),
):
    """Configures project-level, tier-level, or query-data default TTL policies."""
    try:
        return await retention_facade.set_default_ttl(
            project_id=project_id,
            request=payload,
            user=user,
        )
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))


@router.put(
    "/api/v1/projects/{project_id}/datasets/{dataset_id}/hold",
    response_model=DatasetRetentionStateContract,
)
async def set_dataset_retention_hold(
    project_id: str,
    dataset_id: str,
    payload: RetentionHoldRequestContract,
    user: Optional[dict] = Depends(authenticate_user),
):
    """Places or releases a Retention Hold on a specific dataset."""
    try:
        return await retention_facade.set_dataset_hold(
            project_id=project_id,
            dataset_id=dataset_id,
            request=payload,
            user=user,
        )
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(ve))


@router.put(
    "/api/v1/projects/{project_id}/ttl/hold",
    response_model=List[DatasetRetentionStateContract],
)
async def set_project_retention_hold(
    project_id: str,
    payload: RetentionHoldRequestContract,
    user: Optional[dict] = Depends(authenticate_user),
):
    """Places or releases a Retention Hold across all datasets in a project."""
    try:
        return await retention_facade.set_project_hold(
            project_id=project_id,
            retention_hold=payload.retention_hold,
            reason=payload.reason,
            user=user,
        )
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))


@router.post(
    "/api/v1/projects/{project_id}/datasets/{dataset_id}/ttl/restore",
    response_model=DatasetRetentionStateContract,
)
async def restore_soft_deleted_dataset(
    project_id: str,
    dataset_id: str,
    payload: DatasetRestoreRequestContract,
    user: Optional[dict] = Depends(authenticate_user),
):
    """Explicitly restores a SOFT_DELETED dataset or query artifact during its grace period."""
    try:
        return await retention_facade.restore_dataset(
            project_id=project_id,
            dataset_id=dataset_id,
            request=payload,
            user=user,
        )
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except LookupError as le:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(le))
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))


@router.get(
    "/api/v1/projects/{project_id}/ttl/summary",
    response_model=ProjectRetentionSummaryContract,
)
async def get_project_retention_summary(
    project_id: str,
    user: Optional[dict] = Depends(authenticate_user),
):
    """Retrieves the retention lifecycle summary and expiring-soon dashboard for a project."""
    try:
        return await retention_facade.get_project_summary(project_id=project_id, user=user)
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))


@router.post(
    "/api/v1/projects/{project_id}/ttl/cleanup",
    response_model=CleanupJobRunContract,
)
async def trigger_project_cleanup(
    project_id: str,
    payload: Optional[CleanupTriggerRequestContract] = None,
    user: Optional[dict] = Depends(authenticate_user),
):
    """Triggers an on-demand cleanup or dry-run preview scoped to a project."""
    try:
        return await retention_facade.trigger_cleanup(
            project_id=project_id,
            request=payload or CleanupTriggerRequestContract(),
            user=user,
        )
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))


@router.post(
    "/api/v1/retention/cleanup",
    response_model=CleanupJobRunContract,
)
async def trigger_global_cleanup(
    payload: Optional[CleanupTriggerRequestContract] = None,
    user: Optional[dict] = Depends(authenticate_user),
):
    """Triggers a global cleanup or dry-run preview across all projects."""
    try:
        return await retention_facade.trigger_cleanup(
            project_id=None,
            request=payload or CleanupTriggerRequestContract(),
            user=user,
        )
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))


@router.get(
    "/api/v1/projects/{project_id}/ttl/cleanup/runs",
    response_model=List[CleanupJobRunContract],
)
async def list_project_cleanup_runs(
    project_id: str,
    limit: int = Query(default=20, ge=1, le=200),
    user: Optional[dict] = Depends(authenticate_user),
):
    """Lists historical cleanup execution runs for a project."""
    try:
        return await retention_facade.list_cleanup_runs(
            project_id=project_id,
            limit=limit,
            user=user,
        )
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))


@router.get(
    "/api/v1/retention/cleanup/runs",
    response_model=List[CleanupJobRunContract],
)
async def list_global_cleanup_runs(
    limit: int = Query(default=50, ge=1, le=200),
    user: Optional[dict] = Depends(authenticate_user),
):
    """Lists global historical cleanup execution runs."""
    return await retention_facade.list_cleanup_runs(project_id=None, limit=limit, user=user)
