import logging
from typing import List, Optional, Dict, Any
from src.domains.project.operations.project_manager import ProjectManager
from src.domains.project.operations.scoped_ingestion import ScopedIngestionService
from src.domains.project.operations.s3_storage import ProjectS3Storage
from src.domains.project.operations.graph_storage import ProjectGraphStorage
from src.domains.project.models.contract.project import (
    ProjectCreateContract,
    ProjectResponseContract,
    ProjectDatasetContract,
    TabularIngestResponseContract,
    GraphIngestResponseContract,
)

logger = logging.getLogger("artemis.project.facade")


class ProjectFacade:
    """Unified Facade for Project domain operations."""

    def __init__(
        self,
        project_manager: Optional[ProjectManager] = None,
        ingestion_service: Optional[ScopedIngestionService] = None,
        s3_storage: Optional[ProjectS3Storage] = None,
        graph_storage: Optional[ProjectGraphStorage] = None,
    ):
        self.project_manager = project_manager or ProjectManager()
        self.s3_storage = s3_storage or ProjectS3Storage()
        self.graph_storage = graph_storage or ProjectGraphStorage()
        self.ingestion = ingestion_service or ScopedIngestionService(
            project_manager=self.project_manager,
            s3_storage=self.s3_storage,
            graph_storage=self.graph_storage,
        )

    async def create_project(
        self,
        project: ProjectCreateContract,
        creator_user_id: Optional[str] = None,
    ) -> ProjectResponseContract:
        return self.project_manager.create_project(project, creator_user_id=creator_user_id)

    async def get_project(self, project_id: str) -> Optional[ProjectResponseContract]:
        return self.project_manager.get_project(project_id)

    async def list_projects(self) -> List[ProjectResponseContract]:
        return self.project_manager.list_projects()

    async def delete_project(self, project_id: str) -> bool:
        return self.project_manager.delete_project(project_id)

    async def ingest_tabular(
        self,
        project_id: str,
        dataset_name: str,
        data_bytes: bytes,
        filename: str,
        tier: str = "BRONZE",
        ttl_expression: Optional[str] = None,
        timestamp_column: Optional[str] = None,
        overwrite: bool = False,
    ) -> TabularIngestResponseContract:
        return self.ingestion.ingest_tabular(
            project_id=project_id,
            dataset_name=dataset_name,
            data_bytes=data_bytes,
            filename=filename,
            tier=tier,
            ttl_expression=ttl_expression,
            timestamp_column=timestamp_column,
            overwrite=overwrite,
        )

    async def ingest_graph(
        self,
        project_id: str,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
        dataset_name: str = "knowledge_graph",
        ttl_expression: Optional[str] = None,
        overwrite: bool = False,
    ) -> GraphIngestResponseContract:
        return self.ingestion.ingest_graph(
            project_id=project_id,
            nodes=nodes,
            edges=edges,
            dataset_name=dataset_name,
            ttl_expression=ttl_expression,
            overwrite=overwrite,
        )

    async def list_datasets(
        self,
        project_id: str,
        tier: Optional[str] = None,
    ) -> List[ProjectDatasetContract]:
        return self.project_manager.list_datasets(project_id=project_id, tier=tier)
