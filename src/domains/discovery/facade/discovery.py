import logging
from typing import Optional, List, Dict, Any
from typing_extensions import Self

try:
    from src.base.facade import DomainFacade
    from src.security.middleware import get_current_user
    from src.domains.discovery.operations.kdg_graph_store import KDGGraphStore
    from src.domains.discovery.operations.job_repository import IndexJobRepository
    from src.domains.project.operations.membership import ProjectMembershipService
    from src.domains.discovery.models.contract.discovery import (
        WorkspaceKnowledgeContract,
        EntityCorrelationContract,
        LineageContract,
        IndexJobContract,
    )
except ImportError:
    from base.facade import DomainFacade
    from security.middleware import get_current_user
    from domains.discovery.operations.kdg_graph_store import KDGGraphStore
    from domains.discovery.operations.job_repository import IndexJobRepository
    from domains.project.operations.membership import ProjectMembershipService
    from domains.discovery.models.contract.discovery import (
        WorkspaceKnowledgeContract,
        EntityCorrelationContract,
        LineageContract,
        IndexJobContract,
    )

logger = logging.getLogger("artemis.discovery.facade")


class DiscoveryFacade(DomainFacade):
    """Domain facade coordinating Knowledge Discovery Graph queries, scoping, and job operations."""

    def __init__(
        self,
        user: Optional[Any] = None,
        session: Optional[Any] = None,
        graph_store: Optional[KDGGraphStore] = None,
        membership_service: Optional[ProjectMembershipService] = None,
        job_repository: Optional[IndexJobRepository] = None,
    ):
        super().__init__(user=user, session=session)
        self.graph_store = graph_store or KDGGraphStore()
        self.membership_service = membership_service or ProjectMembershipService()
        self.job_repository = job_repository or IndexJobRepository()

    def _resolve_member_projects(self, user: Optional[Any] = None) -> List[str]:
        """Resolves project IDs the requesting user has access to, with admin role bypass."""
        u = user or self.user or get_current_user()
        if not u:
            # Fallback for local CLI/testing when no user profile explicitly injected
            return self.membership_service.list_member_projects(user_id="admin", user_roles=["admin"])

        user_id = u.get("sub") or u.get("username")
        roles = u.get("roles", [])
        return self.membership_service.list_member_projects(user_id=user_id, user_roles=roles)

    def _is_owner_or_admin(self, project_id: str, user: Optional[Any] = None) -> bool:
        """Verifies if user is an owner of the project or has admin role."""
        u = user or self.user or get_current_user()
        if not u:
            return True
        user_id = u.get("sub") or u.get("username")
        roles = u.get("roles", [])
        return self.membership_service.is_owner(project_id=project_id, user_id=user_id, user_roles=roles)

    async def get_workspace_knowledge(
        self,
        project_id: str,
        user: Optional[Any] = None,
    ) -> Optional[WorkspaceKnowledgeContract]:
        """Retrieves knowledge summary for a workspace if user is a member."""
        member_projects = self._resolve_member_projects(user=user)
        if project_id not in member_projects:
            return None

        summary = self.graph_store.get_workspace_knowledge(project_id, member_projects)
        if summary:
            # Check latest job status
            jobs = self.job_repository.list_jobs(project_id)
            if jobs:
                summary.enrichment_status = jobs[0].status
        return summary

    async def find_entities(
        self,
        value: Optional[str] = None,
        entity_type: Optional[str] = None,
        fuzzy: bool = False,
        user: Optional[Any] = None,
    ) -> EntityCorrelationContract:
        """Finds cross-project entity occurrences, strictly scoped to member projects."""
        member_projects = self._resolve_member_projects(user=user)
        return self.graph_store.find_cross_project_entities(
            value=value,
            entity_type=entity_type,
            member_projects=member_projects,
            fuzzy=fuzzy,
        )

    async def get_lineage(
        self,
        project_id: str,
        dataset_id: str,
        depth: int = 10,
        user: Optional[Any] = None,
    ) -> LineageContract:
        """Retrieves data lineage tree for a resource, omitting non-member nodes."""
        member_projects = self._resolve_member_projects(user=user)
        return self.graph_store.get_lineage(
            project_id=project_id,
            dataset_id=dataset_id,
            member_projects=member_projects,
            depth=depth,
        )

    async def reindex(
        self,
        project_id: str,
        dataset_id: Optional[str] = None,
        user: Optional[Any] = None,
    ) -> IndexJobContract:
        """Triggers a re-index job for a project dataset. Requires project owner or admin."""
        if not self._is_owner_or_admin(project_id, user=user):
            raise PermissionError(f"Permission denied: User is not an owner or admin of project '{project_id}'.")

        res_id = dataset_id or "*"
        return self.job_repository.create_job(project_id=project_id, resource_id=res_id, phase="structural")

    async def list_jobs(
        self,
        project_id: str,
        status: Optional[str] = None,
        user: Optional[Any] = None,
    ) -> List[IndexJobContract]:
        """Lists indexing jobs for a project if caller is a member."""
        member_projects = self._resolve_member_projects(user=user)
        if project_id not in member_projects:
            return []
        return self.job_repository.list_jobs(project_id=project_id, status=status)
