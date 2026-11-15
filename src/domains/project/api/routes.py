import base64
import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, status, Depends
from src.domains.project.facade.project import ProjectFacade
from src.security.middleware import authenticate_user
from src.domains.project.models.contract.project import (
    ProjectCreateContract,
    ProjectResponseContract,
    ProjectDatasetContract,
    TabularIngestRequestContract,
    TabularIngestResponseContract,
    GraphIngestRequestContract,
    GraphIngestResponseContract,
)

logger = logging.getLogger("artemis.project.api")

router = APIRouter(prefix="/api/v1/projects", tags=["Project Management"])
project_facade = ProjectFacade()


@router.post("", response_model=ProjectResponseContract, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreateContract,
    user: Optional[dict] = Depends(authenticate_user),
):
    """Creates a new isolated project workspace."""
    try:
        creator_user_id = (user.get("sub") or user.get("username")) if user else "admin"
        return await project_facade.create_project(payload, creator_user_id=creator_user_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating project: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create project.")


@router.get("", response_model=List[ProjectResponseContract])
async def list_projects():
    """Lists all active and registered projects."""
    return await project_facade.list_projects()


@router.get("/{project_id}", response_model=ProjectResponseContract)
async def get_project(project_id: str):
    """Retrieves metadata for a specific project."""
    project = await project_facade.get_project(project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Project '{project_id}' not found.")
    return project


@router.delete("/{project_id}")
async def delete_project(project_id: str):
    """Deletes a project and cascades associated metadata."""
    success = await project_facade.delete_project(project_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Project '{project_id}' not found.")
    return {"status": "DELETED", "project_id": project_id}


@router.post("/{project_id}/ingest/tabular", response_model=TabularIngestResponseContract)
async def ingest_tabular_data(
    project_id: str,
    payload: TabularIngestRequestContract,
):
    """Uploads tabular raw data (CSV, JSON, Parquet) into a project tier partition."""
    project = await project_facade.get_project(project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Project '{project_id}' not found.")

    if payload.content_base64:
        contents = base64.b64decode(payload.content_base64)
    elif payload.content_text:
        contents = payload.content_text.encode("utf-8")
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either 'content_base64' or 'content_text' must be provided.",
        )

    try:
        return await project_facade.ingest_tabular(
            project_id=project_id,
            dataset_name=payload.dataset_name,
            data_bytes=contents,
            filename=payload.filename or f"{payload.dataset_name}.csv",
            tier=payload.tier,
        )
    except Exception as e:
        logger.error(f"Error ingesting tabular data: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{project_id}/ingest/graph", response_model=GraphIngestResponseContract)
async def ingest_graph_data(
    project_id: str,
    payload: GraphIngestRequestContract,
):
    """Ingests nodes and edges tagged with the target project identifier."""
    project = await project_facade.get_project(project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Project '{project_id}' not found.")

    nodes_dict = [n.model_dump() for n in payload.nodes]
    edges_dict = [e.model_dump() for e in payload.edges]
    try:
        return await project_facade.ingest_graph(
            project_id=project_id,
            nodes=nodes_dict,
            edges=edges_dict,
        )
    except Exception as e:
        logger.error(f"Error ingesting graph data: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{project_id}/datasets", response_model=List[ProjectDatasetContract])
async def list_project_datasets(project_id: str, tier: Optional[str] = None):
    """Lists all datasets registered for a specific project."""
    project = await project_facade.get_project(project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Project '{project_id}' not found.")
    return await project_facade.list_datasets(project_id=project_id, tier=tier)


from pydantic import BaseModel


class ProjectQueryRequestContract(BaseModel):
    sql: str


@router.post("/{project_id}/query")
async def execute_project_query(project_id: str, payload: ProjectQueryRequestContract):
    """Executes a scoped DuckDB analytical SQL query against project S3 Parquet partitions."""
    project = await project_facade.get_project(project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Project '{project_id}' not found.")

    from src.domains.analytics.operations.project_query import ProjectQueryExecutor
    executor = ProjectQueryExecutor()
    try:
        return executor.execute_scoped_query(project_id, payload.sql)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying project {project_id}: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{project_id}/runs")
async def list_project_runs(project_id: str):
    """Lists all pipeline execution runs across all pipelines in a project."""
    project = await project_facade.get_project(project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Project '{project_id}' not found.")

    from src.domains.pipeline.facade.pipeline import PipelineFacade
    pipe_facade = PipelineFacade()
    return await pipe_facade.list_pipeline_runs(project_id)


from src.domains.project.models.contract.membership import MemberContract, MemberAddRequestContract
from src.domains.project.operations.membership import ProjectMembershipService

membership_service = ProjectMembershipService()


@router.get("/{project_id}/members", response_model=List[MemberContract])
async def list_project_members(
    project_id: str,
    user: Optional[dict] = Depends(authenticate_user),
):
    """Lists all members of a project workspace (members only)."""
    user_id = user.get("sub") or user.get("username") if user else "admin"
    roles = user.get("roles", []) if user else ["admin"]
    if not membership_service.is_member(project_id, user_id=user_id, user_roles=roles):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Project '{project_id}' not found or access denied.")
    return membership_service.list_members(project_id)


@router.post("/{project_id}/members", response_model=MemberContract, status_code=status.HTTP_201_CREATED)
async def add_project_member(
    project_id: str,
    payload: MemberAddRequestContract,
    user: Optional[dict] = Depends(authenticate_user),
):
    """Adds or updates a project member (owner or admin only)."""
    user_id = user.get("sub") or user.get("username") if user else "admin"
    roles = user.get("roles", []) if user else ["admin"]
    if not membership_service.is_owner(project_id, user_id=user_id, user_roles=roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only project owners or administrators can manage members.")
    try:
        return membership_service.add_member(
            project_id=project_id,
            user_id=payload.user_id,
            role=payload.role,
            added_by=user_id,
        )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))


@router.delete("/{project_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_project_member(
    project_id: str,
    user_id: str,
    user: Optional[dict] = Depends(authenticate_user),
):
    """Removes a member from a project workspace (owner or admin only). Last owner cannot be removed (409)."""
    caller_id = user.get("sub") or user.get("username") if user else "admin"
    roles = user.get("roles", []) if user else ["admin"]
    if not membership_service.is_owner(project_id, user_id=caller_id, user_roles=roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only project owners or administrators can manage members.")
    try:
        removed = membership_service.remove_member(project_id, user_id)
        if not removed:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Member '{user_id}' not found in project '{project_id}'.")
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(ve))

