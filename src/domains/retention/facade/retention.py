import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

try:
    from src.base.facade import DomainFacade
    from src.domains.project.operations.membership import ProjectMembershipService
except ImportError:
    from base.facade import DomainFacade
    from domains.project.operations.membership import ProjectMembershipService


def _safe_get_current_user():
    try:
        from src.security.middleware import get_current_user
        return get_current_user()
    except Exception:
        return None

from src.domains.retention.models.contract.retention import (
    TTLPolicyContract,
    DatasetTTLSetRequestContract,
    ProjectTTLDefaultsRequestContract,
    DatasetRetentionStateContract,
    DatasetPartitionContract,
    RetentionHoldRequestContract,
    DatasetRestoreRequestContract,
    ProjectRetentionSummaryContract,
    CleanupTriggerRequestContract,
    CleanupJobRunContract,
)
from src.domains.retention.operations.retention_repository import RetentionRepository
from src.domains.retention.operations.policy_resolver import PolicyResolver
from src.domains.retention.operations.query_artifact_manager import QueryArtifactManager
from src.domains.retention.operations.cleanup_engine import CleanupEngine

logger = logging.getLogger("artemis.retention.facade")


class RetentionFacade(DomainFacade):
    """Domain facade coordinating dataset & query data TTL policies, holds, restoration, summaries, and auto-cleanup."""

    def __init__(
        self,
        user: Optional[Any] = None,
        session: Optional[Any] = None,
        repository: Optional[RetentionRepository] = None,
        policy_resolver: Optional[PolicyResolver] = None,
        artifact_manager: Optional[QueryArtifactManager] = None,
        cleanup_engine: Optional[CleanupEngine] = None,
        membership_service: Optional[ProjectMembershipService] = None,
    ):
        super().__init__(user=user, session=session)
        self.repo = repository or RetentionRepository()
        self.resolver = policy_resolver or PolicyResolver(repository=self.repo)
        self.artifact_manager = artifact_manager or QueryArtifactManager(
            repository=self.repo,
            policy_resolver=self.resolver,
        )
        self.cleanup_engine = cleanup_engine or CleanupEngine(
            repository=self.repo,
            policy_resolver=self.resolver,
            artifact_manager=self.artifact_manager,
        )
        self.membership_service = membership_service or ProjectMembershipService()

    def _resolve_caller(self, user: Optional[Any] = None) -> Tuple[str, List[str]]:
        u = user or self.user or _safe_get_current_user()
        if not u:
            return "admin", ["admin"]
        user_id = u.get("sub") or u.get("username") or "admin"
        roles = u.get("roles", [])
        return user_id, roles

    def _require_member(self, project_id: str, user: Optional[Any] = None) -> str:
        user_id, roles = self._resolve_caller(user)
        if not self.membership_service.is_member(project_id=project_id, user_id=user_id, user_roles=roles):
            raise PermissionError(f"Access denied: User '{user_id}' is not a member of project '{project_id}'.")
        return user_id

    def _require_owner(self, project_id: str, user: Optional[Any] = None) -> str:
        user_id, roles = self._resolve_caller(user)
        if not self.membership_service.is_owner(project_id=project_id, user_id=user_id, user_roles=roles):
            raise PermissionError(
                f"Permission denied: Only project owners or administrators can modify TTL policies or run live cleanup on '{project_id}'."
            )
        return user_id

    async def set_dataset_ttl(
        self,
        project_id: str,
        dataset_id: str,
        request: DatasetTTLSetRequestContract,
        user: Optional[Any] = None,
        now: Optional[datetime] = None,
    ) -> DatasetRetentionStateContract:
        caller_id = self._require_owner(project_id, user=user)
        return self.resolver.set_dataset_ttl(
            project_id=project_id,
            dataset_id=dataset_id,
            request=request,
            updated_by=caller_id,
            now=now,
        )

    async def get_dataset_ttl(
        self,
        project_id: str,
        dataset_id: str,
        tier: str = "BRONZE",
        user: Optional[Any] = None,
        now: Optional[datetime] = None,
    ) -> DatasetRetentionStateContract:
        self._require_member(project_id, user=user)
        state = self.repo.get_dataset_state(project_id=project_id, dataset_id=dataset_id, tier=tier.upper())
        if not state:
            state = self.resolver.compute_and_persist_dataset_state(
                project_id=project_id,
                dataset_id=dataset_id,
                tier=tier.upper(),
                now=now,
            )
        return self.resolver.enrich_state_metrics(state, now=now)

    async def clear_dataset_ttl(
        self,
        project_id: str,
        dataset_id: str,
        tier: str = "BRONZE",
        user: Optional[Any] = None,
        now: Optional[datetime] = None,
    ) -> DatasetRetentionStateContract:
        self._require_owner(project_id, user=user)
        return self.resolver.clear_dataset_ttl(
            project_id=project_id,
            dataset_id=dataset_id,
            tier=tier.upper(),
            now=now,
        )

    async def set_default_ttl(
        self,
        project_id: str,
        request: ProjectTTLDefaultsRequestContract,
        user: Optional[Any] = None,
        now: Optional[datetime] = None,
    ) -> TTLPolicyContract:
        caller_id = self._require_owner(project_id, user=user)
        return self.resolver.set_default_ttl(
            project_id=project_id,
            request=request,
            updated_by=caller_id,
            now=now,
        )

    async def register_ingested_partition(
        self,
        project_id: str,
        dataset_id: str,
        tier: str,
        object_key: str,
        storage_uri: str,
        size_bytes: int,
        record_count: int,
        ingested_at: Optional[datetime] = None,
        min_event_ts: Optional[datetime] = None,
        max_event_ts: Optional[datetime] = None,
        overwrite: bool = False,
        explicit_ttl_expression: Optional[str] = None,
        timestamp_column: Optional[str] = None,
    ) -> DatasetRetentionStateContract:
        """Records an uploaded partition file and initializes/updates the dataset's retention state."""
        self.repo.add_partition(
            project_id=project_id,
            dataset_id=dataset_id,
            tier=tier.upper(),
            object_key=object_key,
            storage_uri=storage_uri,
            size_bytes=size_bytes,
            record_count=record_count,
            ingested_at=ingested_at,
            min_event_ts=min_event_ts,
            max_event_ts=max_event_ts,
            overwrite=overwrite,
        )
        if explicit_ttl_expression or timestamp_column:
            pol, _ = self.resolver.resolve_effective_dataset_policy(project_id, dataset_id, tier.upper())
            req = DatasetTTLSetRequestContract(
                tier=tier.upper(),
                ttl_expression=explicit_ttl_expression or pol.ttl_expression,
                granularity="TIMESTAMP_COLUMN" if timestamp_column else pol.granularity,
                timestamp_column=timestamp_column or pol.timestamp_column,
                grace_period_expression=pol.grace_period_expression,
            )
            return self.resolver.set_dataset_ttl(project_id, dataset_id, req, now=ingested_at)

        return self.resolver.compute_and_persist_dataset_state(
            project_id=project_id,
            dataset_id=dataset_id,
            tier=tier.upper(),
            reference_timestamp=ingested_at if overwrite else None,
            now=ingested_at,
            allow_implicit_restore=overwrite,
        )

    async def set_dataset_hold(
        self,
        project_id: str,
        dataset_id: str,
        request: RetentionHoldRequestContract,
        user: Optional[Any] = None,
        now: Optional[datetime] = None,
    ) -> DatasetRetentionStateContract:
        caller_id = self._require_owner(project_id, user=user)
        return self.resolver.set_dataset_hold(
            project_id=project_id,
            dataset_id=dataset_id,
            request=request,
            user_id=caller_id,
            now=now,
        )

    async def set_project_hold(
        self,
        project_id: str,
        retention_hold: bool,
        reason: Optional[str] = None,
        user: Optional[Any] = None,
        now: Optional[datetime] = None,
    ) -> List[DatasetRetentionStateContract]:
        caller_id = self._require_owner(project_id, user=user)
        return self.resolver.set_project_hold(
            project_id=project_id,
            retention_hold=retention_hold,
            reason=reason,
            user_id=caller_id,
            now=now,
        )

    async def restore_dataset(
        self,
        project_id: str,
        dataset_id: str,
        request: DatasetRestoreRequestContract,
        user: Optional[Any] = None,
        now: Optional[datetime] = None,
    ) -> DatasetRetentionStateContract:
        caller_id = self._require_owner(project_id, user=user)
        return self.resolver.restore_soft_deleted_dataset(
            project_id=project_id,
            dataset_id=dataset_id,
            request=request,
            user_id=caller_id,
            now=now,
        )

    async def get_project_summary(
        self,
        project_id: str,
        user: Optional[Any] = None,
        now: Optional[datetime] = None,
    ) -> ProjectRetentionSummaryContract:
        self._require_member(project_id, user=user)
        return self.resolver.get_project_retention_summary(project_id=project_id, now=now)

    async def trigger_cleanup(
        self,
        project_id: Optional[str] = None,
        request: Optional[CleanupTriggerRequestContract] = None,
        user: Optional[Any] = None,
        now: Optional[datetime] = None,
    ) -> CleanupJobRunContract:
        req = request or CleanupTriggerRequestContract()
        if project_id:
            if req.dry_run:
                caller_id = self._require_member(project_id, user=user)
            else:
                caller_id = self._require_owner(project_id, user=user)
        else:
            caller_id, roles = self._resolve_caller(user)
            if not req.dry_run and "admin" not in roles and caller_id != "admin":
                raise PermissionError("Permission denied: Global live cleanup requires administrator privileges.")

        return self.cleanup_engine.evaluate_and_cleanup(
            project_id=project_id,
            dry_run=req.dry_run,
            include_query_artifacts=req.include_query_artifacts,
            trigger_type="DRY_RUN" if req.dry_run else "MANUAL",
            initiated_by=caller_id,
            now=now,
        )

    async def list_cleanup_runs(
        self,
        project_id: Optional[str] = None,
        limit: int = 20,
        user: Optional[Any] = None,
    ) -> List[CleanupJobRunContract]:
        if project_id:
            self._require_member(project_id, user=user)
        return self.repo.list_cleanup_runs(project_id=project_id, limit=limit)
