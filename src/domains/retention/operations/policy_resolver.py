import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

try:
    from src.config.settings import settings
except ImportError:
    from config.settings import settings

from src.domains.retention.models.contract.retention import (
    TTLPolicyContract,
    DatasetTTLSetRequestContract,
    ProjectTTLDefaultsRequestContract,
    DatasetRetentionStateContract,
    RetentionHoldRequestContract,
    DatasetRestoreRequestContract,
    ProjectRetentionSummaryContract,
)
from src.domains.retention.operations.ttl_parser import (
    parse_ttl_expression,
    normalize_ttl_expression,
)
from src.domains.retention.operations.retention_repository import RetentionRepository

logger = logging.getLogger("artemis.retention.policy_resolver")


class PolicyResolver:
    """Resolves hierarchical TTL policies (DATASET > TIER > PROJECT > PLATFORM) and manages dataset lifecycle states."""

    def __init__(self, repository: Optional[RetentionRepository] = None):
        self.repo = repository or RetentionRepository()

    def get_platform_default_ttl(self, tier: Optional[str] = None, query_artifact_type: Optional[str] = None) -> str:
        """Returns out-of-the-box platform default TTL expression."""
        if query_artifact_type:
            q_type = query_artifact_type.upper()
            if q_type in ("SQL_RESULT_CACHE", "AI_RAG_CACHE"):
                return getattr(settings, "default_query_cache_ttl", "1h")
            if q_type == "MATERIALIZED_EXPORT":
                return getattr(settings, "default_query_export_ttl", "7d")
            if q_type == "QUERY_HISTORY_LOG":
                return getattr(settings, "default_query_history_ttl", "30d")
            return "1h"

        t = (tier or "BRONZE").upper()
        if t == "BRONZE":
            return getattr(settings, "default_bronze_ttl", "30d")
        if t == "SILVER":
            return getattr(settings, "default_silver_ttl", "90d")
        if t == "GOLD":
            return getattr(settings, "default_gold_ttl", "365d")
        return "30d"

    def resolve_effective_dataset_policy(
        self,
        project_id: str,
        dataset_id: str,
        tier: str = "BRONZE",
    ) -> Tuple[TTLPolicyContract, str]:
        """
        Resolves the effective TTL policy for a dataset following the 4-tier hierarchy:
        1. DATASET_EXPLICIT (target_scope='DATASET' for project_id, tier, dataset_id)
        2. TIER_DEFAULT (target_scope='TIER' for project_id, tier)
        3. PROJECT_DEFAULT (target_scope='PROJECT' for project_id)
        4. PLATFORM_DEFAULT (built-in settings for tier)
        Returns (TTLPolicyContract, policy_source_label).
        """
        tier_up = tier.upper()

        # 1. Dataset-explicit override
        ds_policy = self.repo.get_policy(
            project_id=project_id,
            target_scope="DATASET",
            tier=tier_up,
            dataset_id=dataset_id,
        )
        if ds_policy:
            return ds_policy, "DATASET_EXPLICIT"

        # 2. Project-tier default
        tier_policy = self.repo.get_policy(
            project_id=project_id,
            target_scope="TIER",
            tier=tier_up,
        )
        if tier_policy:
            return tier_policy, "TIER_DEFAULT"

        # 3. Project-wide default
        proj_policy = self.repo.get_policy(
            project_id=project_id,
            target_scope="PROJECT",
        )
        if proj_policy:
            return proj_policy, "PROJECT_DEFAULT"

        # 4. Platform default
        default_expr = self.get_platform_default_ttl(tier=tier_up)
        default_grace = getattr(settings, "default_grace_period", "24h")
        ttl_sec = parse_ttl_expression(default_expr, allow_zero=False, allow_infinite=True)
        grace_sec = parse_ttl_expression(default_grace, allow_zero=True, allow_infinite=False) or 0
        return (
            TTLPolicyContract(
                policy_id=None,
                project_id=project_id,
                target_scope="PLATFORM",
                tier=tier_up,
                dataset_id=dataset_id,
                ttl_expression=default_expr,
                ttl_seconds=ttl_sec,
                granularity="INGESTION_AGE",
                timestamp_column=None,
                grace_period_expression=default_grace,
                grace_period_seconds=grace_sec,
            ),
            "PLATFORM_DEFAULT",
        )

    def resolve_query_artifact_policy(
        self,
        project_id: Optional[str],
        artifact_type: str,
        explicit_ttl_expression: Optional[str] = None,
    ) -> TTLPolicyContract:
        """
        Resolves the effective TTL policy for a query data artifact (cache, export, history log),
        capping explicit user overrides to the project's maximum retention policy if configured.
        """
        art_type = artifact_type.upper()
        default_grace = getattr(settings, "default_grace_period", "24h")
        grace_sec = parse_ttl_expression(default_grace, allow_zero=True, allow_infinite=False) or 0

        # Project max bound if configured
        project_max_seconds: Optional[int] = None
        if project_id:
            proj_policy = self.repo.get_policy(project_id=project_id, target_scope="PROJECT")
            if proj_policy and proj_policy.ttl_seconds is not None:
                project_max_seconds = proj_policy.ttl_seconds

        if explicit_ttl_expression:
            norm_expr = normalize_ttl_expression(explicit_ttl_expression, allow_zero=False, allow_infinite=True)
            req_seconds = parse_ttl_expression(norm_expr, allow_zero=False, allow_infinite=True)
            if project_max_seconds is not None:
                if req_seconds is None or req_seconds > project_max_seconds:
                    raise ValueError(
                        f"Requested query artifact TTL '{explicit_ttl_expression}' exceeds project '{project_id}' "
                        f"maximum retention limit of {proj_policy.ttl_expression}."
                    )
            return TTLPolicyContract(
                project_id=project_id,
                target_scope="QUERY_DATA",
                query_artifact_type=art_type,
                ttl_expression=norm_expr,
                ttl_seconds=req_seconds,
                grace_period_expression=default_grace,
                grace_period_seconds=grace_sec,
            )

        if project_id:
            q_policy = self.repo.get_policy(
                project_id=project_id,
                target_scope="QUERY_DATA",
                query_artifact_type=art_type,
            )
            if q_policy:
                return q_policy

        default_expr = self.get_platform_default_ttl(query_artifact_type=art_type)
        ttl_sec = parse_ttl_expression(default_expr, allow_zero=False, allow_infinite=True)
        return TTLPolicyContract(
            project_id=project_id,
            target_scope="QUERY_DATA",
            query_artifact_type=art_type,
            ttl_expression=default_expr,
            ttl_seconds=ttl_sec,
            grace_period_expression=default_grace,
            grace_period_seconds=grace_sec,
        )

    def compute_and_persist_dataset_state(
        self,
        project_id: str,
        dataset_id: str,
        tier: str = "BRONZE",
        reference_timestamp: Optional[datetime] = None,
        now: Optional[datetime] = None,
        allow_implicit_restore: bool = False,
    ) -> DatasetRetentionStateContract:
        """
        Computes or updates the DatasetRetentionStateContract for a dataset based on active partitions
        and the resolved hierarchical policy.
        Supports implicit restoration from SOFT_DELETED when allow_implicit_restore=True and new TTL/hold is valid.
        """
        tier_up = tier.upper()
        ref_now = now or datetime.now(timezone.utc)
        existing = self.repo.get_dataset_state(project_id, dataset_id, tier_up)
        policy, policy_source = self.resolve_effective_dataset_policy(project_id, dataset_id, tier_up)

        # Determine reference timestamp from earliest active partition or provided timestamp
        partitions = self.repo.list_partitions(project_id, dataset_id=dataset_id, tier=tier_up)
        active_partitions = [p for p in partitions if p.lifecycle_status == "ACTIVE"]

        if reference_timestamp is not None:
            ref_ts = reference_timestamp
        elif active_partitions:
            ref_ts = min(p.ingested_at for p in active_partitions)
        elif existing and existing.reference_timestamp:
            ref_ts = existing.reference_timestamp
        else:
            ref_ts = ref_now

        if ref_ts.tzinfo is None:
            ref_ts = ref_ts.replace(tzinfo=timezone.utc)

        ttl_seconds = policy.ttl_seconds
        expires_at = (ref_ts + timedelta(seconds=ttl_seconds)) if ttl_seconds is not None else None

        hold = existing.retention_hold if existing else False
        hold_reason = existing.hold_reason if existing else None
        held_by = existing.held_by if existing else None
        soft_deleted_at = existing.soft_deleted_at if existing else None
        purge_after = existing.purge_after if existing else None
        purged_at = existing.purged_at if existing else None
        current_status = existing.lifecycle_status if existing else "ACTIVE"
        auto_restored = False

        # Check implicit restoration from SOFT_DELETED if policy was extended or hold is active
        if current_status == "SOFT_DELETED" and allow_implicit_restore:
            if hold or expires_at is None or expires_at > ref_now:
                current_status = "HELD" if hold else "ACTIVE"
                soft_deleted_at = None
                purge_after = None
                auto_restored = True
                # Restore any soft-deleted partitions for this dataset
                for p in partitions:
                    if p.lifecycle_status == "SOFT_DELETED" and p.partition_id:
                        self.repo.update_partition_status(p.partition_id, "ACTIVE", None)
                active_partitions = self.repo.list_partitions(
                    project_id, dataset_id=dataset_id, tier=tier_up, lifecycle_status="ACTIVE"
                )

        # Determine current lifecycle_status
        if current_status == "PURGED":
            new_status = "PURGED"
        elif hold:
            new_status = "HELD"
        elif current_status in ("SOFT_DELETED", "CLEANUP_IN_PROGRESS", "CLEANUP_PENDING_RETRY"):
            new_status = current_status
        else:
            if expires_at is not None:
                remaining = (expires_at - ref_now).total_seconds()
                if remaining <= 86400 and remaining > 0:
                    new_status = "EXPIRING_SOON"
                else:
                    new_status = "ACTIVE"
            else:
                new_status = "ACTIVE"

        state = DatasetRetentionStateContract(
            project_id=project_id,
            dataset_id=dataset_id,
            tier=tier_up,
            effective_policy_id=policy.policy_id,
            policy_source=policy_source,
            effective_ttl_expression=policy.ttl_expression,
            effective_ttl_seconds=policy.ttl_seconds,
            granularity=policy.granularity,
            timestamp_column=policy.timestamp_column,
            grace_period_expression=policy.grace_period_expression,
            grace_period_seconds=policy.grace_period_seconds,
            reference_timestamp=ref_ts,
            expires_at=expires_at,
            soft_deleted_at=soft_deleted_at,
            purge_after=purge_after,
            purged_at=purged_at,
            retention_hold=hold,
            hold_reason=hold_reason,
            held_by=held_by,
            lifecycle_status=new_status,
            last_error=existing.last_error if existing else None,
            last_evaluated_at=ref_now,
            auto_restored=auto_restored,
        )
        saved = self.repo.upsert_dataset_state(state)
        return self.enrich_state_metrics(saved, active_partitions_count=len(active_partitions), now=ref_now)

    def enrich_state_metrics(
        self,
        state: DatasetRetentionStateContract,
        active_partitions_count: Optional[int] = None,
        now: Optional[datetime] = None,
    ) -> DatasetRetentionStateContract:
        """Computes dynamic age_seconds and remaining_seconds for API/CLI presentation."""
        ref_now = now or datetime.now(timezone.utc)
        ref_ts = state.reference_timestamp
        if ref_ts.tzinfo is None:
            ref_ts = ref_ts.replace(tzinfo=timezone.utc)

        state.age_seconds = max(0, int((ref_now - ref_ts).total_seconds()))
        if state.expires_at is not None:
            exp = state.expires_at
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            state.remaining_seconds = max(0, int((exp - ref_now).total_seconds()))
            if (
                state.lifecycle_status == "ACTIVE"
                and not state.retention_hold
                and 0 < state.remaining_seconds <= 86400
            ):
                state.lifecycle_status = "EXPIRING_SOON"
        else:
            state.remaining_seconds = None

        if active_partitions_count is not None:
            state.active_partitions_count = active_partitions_count
        else:
            parts = self.repo.list_partitions(
                state.project_id, dataset_id=state.dataset_id, tier=state.tier, lifecycle_status="ACTIVE"
            )
            state.active_partitions_count = len(parts)
        return state

    def set_dataset_ttl(
        self,
        project_id: str,
        dataset_id: str,
        request: DatasetTTLSetRequestContract,
        updated_by: str = "admin",
        now: Optional[datetime] = None,
    ) -> DatasetRetentionStateContract:
        """Sets or updates an explicit dataset TTL policy and recalculates retention state (with implicit restore support)."""
        ttl_sec = parse_ttl_expression(request.ttl_expression, allow_zero=False, allow_infinite=True)
        grace_sec = parse_ttl_expression(request.grace_period_expression, allow_zero=True, allow_infinite=False) or 0

        policy = TTLPolicyContract(
            project_id=project_id,
            target_scope="DATASET",
            tier=request.tier.upper(),
            dataset_id=dataset_id,
            ttl_expression=request.ttl_expression,
            ttl_seconds=ttl_sec,
            granularity=request.granularity,
            timestamp_column=request.timestamp_column,
            grace_period_expression=request.grace_period_expression,
            grace_period_seconds=grace_sec,
            updated_by=updated_by,
        )
        self.repo.upsert_policy(policy)
        return self.compute_and_persist_dataset_state(
            project_id=project_id,
            dataset_id=dataset_id,
            tier=request.tier.upper(),
            now=now,
            allow_implicit_restore=True,
        )

    def clear_dataset_ttl(
        self,
        project_id: str,
        dataset_id: str,
        tier: str = "BRONZE",
        now: Optional[datetime] = None,
    ) -> DatasetRetentionStateContract:
        """Removes dataset-explicit TTL override and recalculates state from inherited tier/project default."""
        self.repo.delete_dataset_policy(project_id=project_id, dataset_id=dataset_id, tier=tier.upper())
        return self.compute_and_persist_dataset_state(
            project_id=project_id,
            dataset_id=dataset_id,
            tier=tier.upper(),
            now=now,
            allow_implicit_restore=True,
        )

    def set_default_ttl(
        self,
        project_id: str,
        request: ProjectTTLDefaultsRequestContract,
        updated_by: str = "admin",
        now: Optional[datetime] = None,
    ) -> TTLPolicyContract:
        """Configures a project-wide, tier-level, or query-data default TTL policy and updates inherited datasets."""
        ttl_sec = parse_ttl_expression(request.ttl_expression, allow_zero=False, allow_infinite=True)
        grace_sec = parse_ttl_expression(request.grace_period_expression, allow_zero=True, allow_infinite=False) or 0

        policy = TTLPolicyContract(
            project_id=project_id,
            target_scope=request.target_scope,
            tier=request.tier.upper() if request.tier else None,
            query_artifact_type=request.query_artifact_type,
            ttl_expression=request.ttl_expression,
            ttl_seconds=ttl_sec,
            granularity="INGESTION_AGE",
            grace_period_expression=request.grace_period_expression,
            grace_period_seconds=grace_sec,
            updated_by=updated_by,
        )
        saved_policy = self.repo.upsert_policy(policy)

        # Recalculate states for datasets in this project that inherit defaults
        if request.target_scope in ("PROJECT", "TIER"):
            states = self.repo.list_dataset_states(project_id=project_id)
            for st in states:
                if st.policy_source != "DATASET_EXPLICIT" and st.lifecycle_status != "PURGED":
                    if request.target_scope == "PROJECT" or st.tier == (request.tier or "").upper():
                        self.compute_and_persist_dataset_state(
                            project_id=project_id,
                            dataset_id=st.dataset_id,
                            tier=st.tier,
                            now=now,
                        )
        return saved_policy

    def set_dataset_hold(
        self,
        project_id: str,
        dataset_id: str,
        request: RetentionHoldRequestContract,
        user_id: str = "admin",
        now: Optional[datetime] = None,
    ) -> DatasetRetentionStateContract:
        """Toggles a Retention Hold on a specific dataset; placing a hold on a SOFT_DELETED dataset implicitly restores it."""
        ref_now = now or datetime.now(timezone.utc)
        tier_up = request.tier.upper()
        state = self.repo.get_dataset_state(project_id, dataset_id, tier_up)
        if not state:
            state = self.compute_and_persist_dataset_state(project_id, dataset_id, tier_up, now=ref_now)

        if state.lifecycle_status == "PURGED":
            raise ValueError(f"Cannot modify retention hold: dataset '{dataset_id}' ({tier_up}) has already been PURGED.")

        auto_restored = False
        state.retention_hold = request.retention_hold
        state.hold_reason = request.reason if request.retention_hold else None
        state.held_by = user_id if request.retention_hold else None

        if request.retention_hold:
            if state.lifecycle_status == "SOFT_DELETED":
                auto_restored = True
                state.soft_deleted_at = None
                state.purge_after = None
                for p in self.repo.list_partitions(project_id, dataset_id=dataset_id, tier=tier_up):
                    if p.lifecycle_status == "SOFT_DELETED" and p.partition_id:
                        self.repo.update_partition_status(p.partition_id, "ACTIVE", None)
                self._sync_graph_resource_status(project_id, dataset_id, "ACTIVE")
            state.lifecycle_status = "HELD"
        else:
            state.lifecycle_status = "ACTIVE"

        state.auto_restored = auto_restored
        saved = self.repo.upsert_dataset_state(state)
        if not request.retention_hold:
            return self.compute_and_persist_dataset_state(project_id, dataset_id, tier_up, now=ref_now)
        return self.enrich_state_metrics(saved, now=ref_now)

    def set_project_hold(
        self,
        project_id: str,
        retention_hold: bool,
        reason: Optional[str] = None,
        user_id: str = "admin",
        now: Optional[datetime] = None,
    ) -> List[DatasetRetentionStateContract]:
        """Places or releases a Retention Hold across all non-purged datasets in a project."""
        states = self.repo.list_dataset_states(project_id=project_id)
        updated: List[DatasetRetentionStateContract] = []
        for st in states:
            if st.lifecycle_status == "PURGED":
                continue
            req = RetentionHoldRequestContract(tier=st.tier, retention_hold=retention_hold, reason=reason)
            updated.append(self.set_dataset_hold(project_id, st.dataset_id, req, user_id=user_id, now=now))
        return updated

    def restore_soft_deleted_dataset(
        self,
        project_id: str,
        dataset_id: str,
        request: DatasetRestoreRequestContract,
        user_id: str = "admin",
        now: Optional[datetime] = None,
    ) -> DatasetRetentionStateContract:
        """
        Explicitly restores a SOFT_DELETED dataset (or materialized query export) back to ACTIVE/HELD
        during its grace period, requiring either a non-expired TTL extension or a Retention Hold (FR-006).
        """
        ref_now = now or datetime.now(timezone.utc)
        tier_up = request.tier.upper()
        state = self.repo.get_dataset_state(project_id, dataset_id, tier_up)

        # Also check if dataset_id refers to a SOFT_DELETED materialized query export
        artifact = self.repo.get_query_artifact(dataset_id) if not state else None
        if artifact and not state:
            if artifact.lifecycle_status == "PURGED":
                raise LookupError(f"Query artifact '{dataset_id}' has already been permanently PURGED and cannot be restored.")
            if request.ttl_expression:
                new_sec = parse_ttl_expression(request.ttl_expression, allow_zero=False, allow_infinite=True)
                artifact.ttl_expression = normalize_ttl_expression(request.ttl_expression)
                artifact.ttl_seconds = new_sec
                artifact.expires_at = (ref_now + timedelta(seconds=new_sec)) if new_sec is not None else None
            if request.retention_hold:
                artifact.retention_hold = True
            artifact.lifecycle_status = "ACTIVE"
            artifact.soft_deleted_at = None
            artifact.purge_after = None
            self.repo.upsert_query_artifact(artifact)
            return DatasetRetentionStateContract(
                project_id=project_id,
                dataset_id=dataset_id,
                tier=tier_up,
                policy_source="QUERY_ARTIFACT",
                effective_ttl_expression=artifact.ttl_expression,
                effective_ttl_seconds=artifact.ttl_seconds,
                reference_timestamp=artifact.created_at,
                expires_at=artifact.expires_at,
                retention_hold=artifact.retention_hold,
                hold_reason=request.reason,
                held_by=user_id if request.retention_hold else None,
                lifecycle_status="HELD" if artifact.retention_hold else "ACTIVE",
                auto_restored=True,
            )

        if not state:
            raise ValueError(f"Dataset '{dataset_id}' (tier '{tier_up}') not found in project '{project_id}'.")

        if state.lifecycle_status == "PURGED":
            raise LookupError(
                f"Dataset '{dataset_id}' (tier '{tier_up}') has already been permanently PURGED and cannot be restored."
            )

        # Apply new TTL if provided
        if request.ttl_expression:
            ttl_sec = parse_ttl_expression(request.ttl_expression, allow_zero=False, allow_infinite=True)
            ref_ts = state.reference_timestamp
            if ref_ts.tzinfo is None:
                ref_ts = ref_ts.replace(tzinfo=timezone.utc)
            if ttl_sec is not None and (ref_ts + timedelta(seconds=ttl_sec)) <= ref_now and not request.retention_hold:
                # Anchor from reference_timestamp or shift reference so it does not immediately re-expire
                new_expires = ref_ts + timedelta(seconds=ttl_sec)
                if new_expires <= ref_now:
                    raise ValueError(
                        f"Provided TTL '{request.ttl_expression}' would still be expired relative to dataset ingestion timestamp "
                        f"({ref_ts.isoformat()}). Specify a longer TTL or enable retention_hold."
                    )
            set_req = DatasetTTLSetRequestContract(
                tier=tier_up,
                ttl_expression=request.ttl_expression,
                granularity=state.granularity,
                timestamp_column=state.timestamp_column,
                grace_period_expression=state.grace_period_expression,
            )
            state = self.set_dataset_ttl(project_id, dataset_id, set_req, updated_by=user_id, now=ref_now)

        if request.retention_hold:
            hold_req = RetentionHoldRequestContract(tier=tier_up, retention_hold=True, reason=request.reason)
            state = self.set_dataset_hold(project_id, dataset_id, hold_req, user_id=user_id, now=ref_now)

        if state.lifecycle_status == "SOFT_DELETED":
            state.lifecycle_status = "HELD" if state.retention_hold else "ACTIVE"
            state.soft_deleted_at = None
            state.purge_after = None
            state = self.repo.upsert_dataset_state(state)

        for p in self.repo.list_partitions(project_id, dataset_id=dataset_id, tier=tier_up):
            if p.lifecycle_status == "SOFT_DELETED" and p.partition_id:
                self.repo.update_partition_status(p.partition_id, "ACTIVE", None)

        self._sync_graph_resource_status(project_id, dataset_id, "ACTIVE")
        state.auto_restored = True
        return self.enrich_state_metrics(state, now=ref_now)

    def _sync_graph_resource_status(self, project_id: str, dataset_id: str, lifecycle_status: str) -> None:
        """Best-effort synchronization of DataResource.lifecycle_status in Memgraph."""
        try:
            from src.domains.discovery.operations.kdg_graph_store import KDGGraphStore
            KDGGraphStore().set_resource_lifecycle_status(project_id, dataset_id, lifecycle_status)
        except Exception as e:
            logger.debug(f"Could not sync graph resource lifecycle status: {e}")

    def get_project_retention_summary(
        self,
        project_id: str,
        now: Optional[datetime] = None,
    ) -> ProjectRetentionSummaryContract:
        """Builds the complete retention governance dashboard summary for a project workspace."""
        ref_now = now or datetime.now(timezone.utc)
        states = self.repo.list_dataset_states(project_id=project_id)
        tombstones = self.repo.list_tombstones(project_id=project_id)
        artifacts = self.repo.list_query_artifacts(project_id=project_id)

        default_policies = {
            "BRONZE": self.resolve_effective_dataset_policy(project_id, "__default__", "BRONZE")[0].ttl_expression,
            "SILVER": self.resolve_effective_dataset_policy(project_id, "__default__", "SILVER")[0].ttl_expression,
            "GOLD": self.resolve_effective_dataset_policy(project_id, "__default__", "GOLD")[0].ttl_expression,
            "SQL_RESULT_CACHE": self.resolve_query_artifact_policy(project_id, "SQL_RESULT_CACHE").ttl_expression,
            "AI_RAG_CACHE": self.resolve_query_artifact_policy(project_id, "AI_RAG_CACHE").ttl_expression,
            "MATERIALIZED_EXPORT": self.resolve_query_artifact_policy(project_id, "MATERIALIZED_EXPORT").ttl_expression,
            "QUERY_HISTORY_LOG": self.resolve_query_artifact_policy(project_id, "QUERY_HISTORY_LOG").ttl_expression,
        }

        counts = {
            "active": 0,
            "expiring_within_24h": 0,
            "held": 0,
            "soft_deleted": 0,
            "purged_tombstones": len(tombstones),
        }
        datasets_list: List[Dict[str, Any]] = []
        for st in states:
            enriched = self.enrich_state_metrics(st, now=ref_now)
            if enriched.lifecycle_status == "HELD" or enriched.retention_hold:
                counts["held"] += 1
            elif enriched.lifecycle_status == "SOFT_DELETED":
                counts["soft_deleted"] += 1
            elif enriched.lifecycle_status in ("ACTIVE", "EXPIRING_SOON"):
                counts["active"] += 1
                if enriched.remaining_seconds is not None and enriched.remaining_seconds <= 86400:
                    counts["expiring_within_24h"] += 1

            datasets_list.append(
                {
                    "dataset_id": enriched.dataset_id,
                    "tier": enriched.tier,
                    "policy_source": enriched.policy_source,
                    "effective_ttl_expression": enriched.effective_ttl_expression,
                    "granularity": enriched.granularity,
                    "timestamp_column": enriched.timestamp_column,
                    "age_seconds": enriched.age_seconds,
                    "remaining_seconds": enriched.remaining_seconds,
                    "expires_at": enriched.expires_at.isoformat() if enriched.expires_at else None,
                    "soft_deleted_at": enriched.soft_deleted_at.isoformat() if enriched.soft_deleted_at else None,
                    "purge_after": enriched.purge_after.isoformat() if enriched.purge_after else None,
                    "retention_hold": enriched.retention_hold,
                    "hold_reason": enriched.hold_reason,
                    "lifecycle_status": enriched.lifecycle_status,
                    "active_partitions_count": enriched.active_partitions_count,
                }
            )

        active_artifacts = [a for a in artifacts if a.lifecycle_status == "ACTIVE"]
        q_summary = {
            "active_caches": sum(1 for a in active_artifacts if a.artifact_type in ("SQL_RESULT_CACHE", "AI_RAG_CACHE")),
            "materialized_exports": sum(1 for a in active_artifacts if a.artifact_type == "MATERIALIZED_EXPORT"),
            "query_history_logs": sum(1 for a in active_artifacts if a.artifact_type == "QUERY_HISTORY_LOG"),
            "total_size_bytes": sum(a.size_bytes for a in active_artifacts),
        }

        return ProjectRetentionSummaryContract(
            project_id=project_id,
            default_policies=default_policies,
            counts=counts,
            datasets=datasets_list,
            query_artifacts_summary=q_summary,
            tombstones=[t.model_dump(mode="json") for t in tombstones],
        )
