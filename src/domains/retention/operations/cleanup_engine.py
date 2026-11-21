import time
import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from src.domains.retention.models.contract.retention import (
    CleanupJobRunContract,
    LineageTombstoneContract,
)
from src.domains.retention.operations.retention_repository import RetentionRepository
from src.domains.retention.operations.policy_resolver import PolicyResolver
from src.domains.retention.operations.query_artifact_manager import QueryArtifactManager
from src.domains.retention.operations.parquet_compactor import ParquetCompactor

logger = logging.getLogger("artemis.retention.cleanup_engine")


class CleanupEngine:
    """
    Coordinates two-stage dataset & query artifact TTL cleanup across PostgreSQL, MinIO, Memgraph, and Redis:
    - Stage 1 (ACTIVE -> SOFT_DELETED): When dataset/partition TTL expires and grace_period > 0, marks SOFT_DELETED
      (immediately hidden from queries and invalidates dependent ephemeral caches).
    - Stage 2 (SOFT_DELETED -> PURGED, or immediate when grace_period == 0): Deletes S3 objects, compacts
      TIMESTAMP_COLUMN Parquet files once TTL + grace_period elapses, prunes reference-counted Memgraph entities,
      preserves LineageTombstones when downstream lineage exists, and records an immutable CleanupJobRun audit log.
    - Respects Retention Holds (`retention_hold = True` -> skipped) and Active Operation Leases (`has_active_lease` -> skipped).
    - Recovers transient multi-store errors via `CLEANUP_PENDING_RETRY`.
    """

    def __init__(
        self,
        repository: Optional[RetentionRepository] = None,
        policy_resolver: Optional[PolicyResolver] = None,
        artifact_manager: Optional[QueryArtifactManager] = None,
        parquet_compactor: Optional[ParquetCompactor] = None,
        s3_storage: Optional[Any] = None,
        graph_store: Optional[Any] = None,
    ):
        self.repo = repository or RetentionRepository()
        self.resolver = policy_resolver or PolicyResolver(repository=self.repo)
        self._s3_storage = s3_storage
        self._graph_store = graph_store
        self.artifact_manager = artifact_manager or QueryArtifactManager(
            repository=self.repo,
            policy_resolver=self.resolver,
            s3_storage=self._s3_storage,
        )
        self.compactor = parquet_compactor or ParquetCompactor(s3_storage=self._s3_storage)

    @property
    def s3_storage(self):
        if self._s3_storage is None:
            try:
                from src.domains.project.operations.s3_storage import ProjectS3Storage
                self._s3_storage = ProjectS3Storage()
            except Exception:
                self._s3_storage = None
        return self._s3_storage

    @property
    def graph_store(self):
        if self._graph_store is None:
            try:
                from src.domains.discovery.operations.kdg_graph_store import KDGGraphStore
                self._graph_store = KDGGraphStore()
            except Exception:
                self._graph_store = None
        return self._graph_store

    def evaluate_and_cleanup(
        self,
        project_id: Optional[str] = None,
        dry_run: bool = False,
        include_query_artifacts: bool = True,
        trigger_type: Optional[str] = None,
        initiated_by: str = "system",
        now: Optional[datetime] = None,
    ) -> CleanupJobRunContract:
        """Executes a scheduled, manual, or dry-run cleanup pass."""
        start_mono = time.monotonic()
        ref_now = now or datetime.now(timezone.utc)
        run_id = str(uuid.uuid4())
        trig = "DRY_RUN" if dry_run else (trigger_type or "MANUAL")

        run = CleanupJobRunContract(
            run_id=run_id,
            trigger_type=trig,
            project_id=project_id,
            initiated_by=initiated_by,
            status="RUNNING",
            started_at=ref_now,
        )

        # Clean up any expired operation leases first
        if not dry_run:
            try:
                self.repo.cleanup_expired_leases(now=ref_now)
            except Exception as e:
                logger.debug(f"Lease cleanup notice: {e}")

        states = self.repo.list_dataset_states(project_id=project_id)
        for st in states:
            if st.lifecycle_status == "PURGED":
                continue

            run.datasets_evaluated += 1

            # 1. Check Retention Hold
            if st.retention_hold or st.lifecycle_status == "HELD":
                run.skipped_held_count += 1
                run.candidate_items.append(
                    {
                        "item_type": "DATASET",
                        "project_id": st.project_id,
                        "dataset_id": st.dataset_id,
                        "tier": st.tier,
                        "action": "SKIP_HELD",
                        "bytes_reclaimed": 0,
                        "reason": f"Retention hold active ({st.hold_reason or 'held'})",
                    }
                )
                continue

            # 2. Check Infinite TTL
            if st.effective_ttl_seconds is None:
                continue

            # 3. Check Active Operation Lease
            if self.repo.has_active_lease(st.project_id, st.dataset_id, now=ref_now):
                run.skipped_locked_count += 1
                run.candidate_items.append(
                    {
                        "item_type": "DATASET",
                        "project_id": st.project_id,
                        "dataset_id": st.dataset_id,
                        "tier": st.tier,
                        "action": "SKIP_LOCKED",
                        "bytes_reclaimed": 0,
                        "reason": "Dataset is currently locked by an active ingestion, pipeline, or query operation",
                    }
                )
                continue

            # 4. Evaluate Row/Partition TIMESTAMP_COLUMN Granularity vs. Whole-Dataset/Partition INGESTION_AGE
            if st.granularity == "TIMESTAMP_COLUMN" and st.timestamp_column:
                self._process_timestamp_column_dataset(st, run, ref_now, dry_run=dry_run)
            else:
                self._process_ingestion_age_dataset(st, run, ref_now, dry_run=dry_run)

        # 5. Evaluate Query Data Artifacts
        if include_query_artifacts:
            self._process_query_artifacts(project_id, run, ref_now, dry_run=dry_run)

        run.completed_at = datetime.now(timezone.utc)
        run.duration_ms = max(1, int((time.monotonic() - start_mono) * 1000))
        if run.errors:
            run.status = "PARTIAL_FAILURE"
        else:
            run.status = "SUCCESS"

        return self.repo.record_cleanup_run(run)

    def _process_ingestion_age_dataset(
        self,
        st,
        run: CleanupJobRunContract,
        ref_now: datetime,
        dry_run: bool,
    ) -> None:
        ttl_sec = st.effective_ttl_seconds
        grace_sec = st.grace_period_seconds
        partitions = self.repo.list_partitions(st.project_id, dataset_id=st.dataset_id, tier=st.tier)
        non_purged_parts = [p for p in partitions if p.lifecycle_status != "PURGED"]

        # Evaluate individual partitions first when multiple appended batch files exist
        if len(non_purged_parts) > 1:
            all_purged_or_expired = True
            for p in non_purged_parts:
                ing_ts = p.ingested_at if p.ingested_at.tzinfo else p.ingested_at.replace(tzinfo=timezone.utc)
                p_exp = ing_ts + timedelta(seconds=ttl_sec)
                if p.lifecycle_status == "ACTIVE" and ref_now >= p_exp:
                    if grace_sec > 0:
                        all_purged_or_expired = False
                        run.datasets_soft_deleted += 1
                        run.candidate_items.append(
                            {
                                "item_type": "DATASET",
                                "project_id": st.project_id,
                                "dataset_id": st.dataset_id,
                                "tier": st.tier,
                                "partition_id": p.partition_id,
                                "action": "SOFT_DELETE",
                                "bytes_reclaimed": 0,
                                "reason": f"Partition expired (TTL {st.effective_ttl_expression}); entering {st.grace_period_expression} grace period",
                            }
                        )
                        if not dry_run and p.partition_id:
                            self.repo.update_partition_status(p.partition_id, "SOFT_DELETED", ref_now)
                            self.artifact_manager.invalidate_ephemeral_caches_for_dataset(st.project_id, st.dataset_id)
                    else:
                        self._purge_single_partition(st, p, run, dry_run=dry_run)
                elif p.lifecycle_status == "SOFT_DELETED":
                    sd_at = (p.soft_deleted_at or p_exp)
                    if sd_at.tzinfo is None:
                        sd_at = sd_at.replace(tzinfo=timezone.utc)
                    if ref_now >= (sd_at + timedelta(seconds=grace_sec)):
                        self._purge_single_partition(st, p, run, dry_run=dry_run)
                    else:
                        all_purged_or_expired = False
                else:
                    all_purged_or_expired = False

            if not dry_run:
                remaining = [
                    p
                    for p in self.repo.list_partitions(st.project_id, dataset_id=st.dataset_id, tier=st.tier)
                    if p.lifecycle_status != "PURGED"
                ]
                if not remaining:
                    self._finalize_dataset_purge(st, run, ref_now, bytes_from_parts=0)
                else:
                    self.resolver.compute_and_persist_dataset_state(
                        st.project_id, st.dataset_id, st.tier, now=ref_now
                    )
            return

        # Single-partition or monolithic dataset evaluation
        ref_ts = st.reference_timestamp
        if ref_ts.tzinfo is None:
            ref_ts = ref_ts.replace(tzinfo=timezone.utc)
        expires_at = st.expires_at or (ref_ts + timedelta(seconds=ttl_sec))
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        total_bytes = sum(p.size_bytes for p in non_purged_parts)

        # Case A: Retry pending or SOFT_DELETED whose grace period has elapsed -> Stage 2 Permanent Purge
        if st.lifecycle_status in ("SOFT_DELETED", "CLEANUP_PENDING_RETRY"):
            purge_after = st.purge_after
            if purge_after is None:
                sd_ts = st.soft_deleted_at or expires_at
                if sd_ts.tzinfo is None:
                    sd_ts = sd_ts.replace(tzinfo=timezone.utc)
                purge_after = sd_ts + timedelta(seconds=grace_sec)
            elif purge_after.tzinfo is None:
                purge_after = purge_after.replace(tzinfo=timezone.utc)

            if st.lifecycle_status == "CLEANUP_PENDING_RETRY" or ref_now >= purge_after:
                run.candidate_items.append(
                    {
                        "item_type": "DATASET",
                        "project_id": st.project_id,
                        "dataset_id": st.dataset_id,
                        "tier": st.tier,
                        "action": "PURGE",
                        "bytes_reclaimed": total_bytes,
                        "reason": f"Grace period elapsed (TTL {st.effective_ttl_expression} + {st.grace_period_expression} grace)",
                    }
                )
                if dry_run:
                    run.datasets_purged += 1
                    run.bytes_reclaimed += total_bytes
                else:
                    self._execute_full_dataset_purge(st, non_purged_parts, total_bytes, run, ref_now)
            return

        # Case B: ACTIVE / EXPIRING_SOON dataset reaching TTL expiration
        if ref_now >= expires_at:
            if grace_sec > 0:
                # Stage 1: Transition to SOFT_DELETED
                run.datasets_soft_deleted += 1
                run.candidate_items.append(
                    {
                        "item_type": "DATASET",
                        "project_id": st.project_id,
                        "dataset_id": st.dataset_id,
                        "tier": st.tier,
                        "action": "SOFT_DELETE",
                        "bytes_reclaimed": 0,
                        "reason": f"TTL ({st.effective_ttl_expression}) elapsed; entering {st.grace_period_expression} soft-delete grace period",
                    }
                )
                if not dry_run:
                    st.lifecycle_status = "SOFT_DELETED"
                    st.soft_deleted_at = ref_now
                    st.purge_after = ref_now + timedelta(seconds=grace_sec)
                    self.repo.upsert_dataset_state(st)
                    for p in non_purged_parts:
                        if p.partition_id:
                            self.repo.update_partition_status(p.partition_id, "SOFT_DELETED", ref_now)
                    self.artifact_manager.invalidate_ephemeral_caches_for_dataset(st.project_id, st.dataset_id)
                    if self.graph_store is not None:
                        try:
                            self.graph_store.set_resource_lifecycle_status(
                                st.project_id, st.dataset_id, "SOFT_DELETED"
                            )
                        except Exception as ge:
                            logger.debug(f"Graph soft-delete status sync notice: {ge}")
            else:
                # Grace period is 0h -> Immediate permanent purge!
                run.candidate_items.append(
                    {
                        "item_type": "DATASET",
                        "project_id": st.project_id,
                        "dataset_id": st.dataset_id,
                        "tier": st.tier,
                        "action": "PURGE",
                        "bytes_reclaimed": total_bytes,
                        "reason": f"TTL ({st.effective_ttl_expression}) elapsed with 0h grace period (immediate purge)",
                    }
                )
                if dry_run:
                    run.datasets_purged += 1
                    run.bytes_reclaimed += total_bytes
                else:
                    self._execute_full_dataset_purge(st, non_purged_parts, total_bytes, run, ref_now)

    def _purge_single_partition(self, st, partition, run: CleanupJobRunContract, dry_run: bool) -> None:
        run.candidate_items.append(
            {
                "item_type": "DATASET",
                "project_id": st.project_id,
                "dataset_id": st.dataset_id,
                "tier": st.tier,
                "partition_id": partition.partition_id,
                "action": "PURGE",
                "bytes_reclaimed": partition.size_bytes,
                "reason": "Partition grace period elapsed",
            }
        )
        if dry_run:
            run.bytes_reclaimed += partition.size_bytes
            return

        if self.s3_storage is not None:
            try:
                self.s3_storage.client.remove_object(self.s3_storage.bucket, partition.object_key)
            except Exception as e:
                logger.warning(f"S3 partition delete error for {partition.object_key}: {e}")
                run.errors.append(
                    {"dataset_id": st.dataset_id, "partition_id": partition.partition_id, "error": str(e)}
                )
                return
        if partition.partition_id:
            self.repo.update_partition_status(partition.partition_id, "PURGED", partition.soft_deleted_at)
        run.bytes_reclaimed += partition.size_bytes
        self.artifact_manager.invalidate_ephemeral_caches_for_dataset(st.project_id, st.dataset_id)

    def _process_timestamp_column_dataset(
        self,
        st,
        run: CleanupJobRunContract,
        ref_now: datetime,
        dry_run: bool,
    ) -> None:
        """
        Evaluates row-level TIMESTAMP_COLUMN datasets:
        - Rows between (now - TTL - grace) and (now - TTL) are virtually soft-deleted at query time.
        - Once a partition has rows older than `purge_cutoff = now - TTL - grace_period`, compacts the Parquet file.
        """
        ttl_sec = st.effective_ttl_seconds
        grace_sec = st.grace_period_seconds
        active_cutoff = ref_now - timedelta(seconds=ttl_sec)
        purge_cutoff = ref_now - timedelta(seconds=(ttl_sec + grace_sec))

        partitions = [
            p
            for p in self.repo.list_partitions(st.project_id, dataset_id=st.dataset_id, tier=st.tier)
            if p.lifecycle_status != "PURGED"
        ]
        for p in partitions:
            try:
                res = self.compactor.compact_s3_partition(
                    partition=p,
                    timestamp_column=st.timestamp_column,
                    active_cutoff_utc=active_cutoff,
                    purge_cutoff_utc=purge_cutoff,
                    dry_run=dry_run,
                )
                if res.action == "NO_OP":
                    continue

                run.partitions_compacted += 1
                run.rows_pruned += res.rows_pruned
                run.bytes_reclaimed += res.bytes_reclaimed
                run.candidate_items.append(
                    {
                        "item_type": "PARTITION_COMPACTION",
                        "project_id": st.project_id,
                        "dataset_id": st.dataset_id,
                        "tier": st.tier,
                        "partition_id": p.partition_id,
                        "action": "COMPACT_ROWS" if res.action == "COMPACTED" else "PURGE",
                        "rows_pruned": res.rows_pruned,
                        "bytes_reclaimed": res.bytes_reclaimed,
                        "reason": f"Pruned rows with {st.timestamp_column} < {active_cutoff.isoformat()}",
                    }
                )
                if not dry_run and p.partition_id:
                    if res.action == "DROPPED_ENTIRE_FILE":
                        self.repo.update_partition_status(p.partition_id, "PURGED", ref_now)
                    elif res.action == "COMPACTED" and res.new_object_key and res.new_storage_uri:
                        self.repo.update_compacted_partition(
                            partition_id=p.partition_id,
                            new_object_key=res.new_object_key,
                            new_storage_uri=res.new_storage_uri,
                            new_size_bytes=res.bytes_after,
                            new_record_count=res.rows_after,
                            new_min_event_ts=res.new_min_event_ts,
                            new_max_event_ts=res.new_max_event_ts,
                        )
                    self.artifact_manager.invalidate_ephemeral_caches_for_dataset(st.project_id, st.dataset_id)
            except Exception as e:
                logger.error(f"Error compacting partition {p.partition_id} for {st.project_id}/{st.dataset_id}: {e}")
                run.errors.append(
                    {"project_id": st.project_id, "dataset_id": st.dataset_id, "error": str(e)}
                )
                if not dry_run:
                    st.lifecycle_status = "CLEANUP_PENDING_RETRY"
                    st.last_error = str(e)
                    self.repo.upsert_dataset_state(st)

    def _execute_full_dataset_purge(
        self,
        st,
        partitions: List[Any],
        total_bytes: int,
        run: CleanupJobRunContract,
        ref_now: datetime,
    ) -> None:
        """Atomically coordinates multi-store purge across Redis, MinIO, Memgraph, and PostgreSQL (FR-008, FR-009)."""
        try:
            # 1. Invalidate dependent ephemeral SQL/AI caches
            self.artifact_manager.invalidate_ephemeral_caches_for_dataset(st.project_id, st.dataset_id)

            # 2. Remove S3 partition objects
            for p in partitions:
                if self.s3_storage is not None and p.object_key:
                    self.s3_storage.client.remove_object(self.s3_storage.bucket, p.object_key)
                if p.partition_id:
                    self.repo.update_partition_status(p.partition_id, "PURGED", st.soft_deleted_at or ref_now)

            self._finalize_dataset_purge(st, run, ref_now, bytes_from_parts=total_bytes)
        except Exception as e:
            logger.error(f"Multi-store purge failed for {st.project_id}/{st.dataset_id}: {e}")
            st.lifecycle_status = "CLEANUP_PENDING_RETRY"
            st.last_error = str(e)
            self.repo.upsert_dataset_state(st)
            run.errors.append({"project_id": st.project_id, "dataset_id": st.dataset_id, "error": str(e)})

    def _finalize_dataset_purge(
        self,
        st,
        run: CleanupJobRunContract,
        ref_now: datetime,
        bytes_from_parts: int,
    ) -> None:
        # 3. Prune Memgraph entities with reference counting & convert to LineageTombstone if lineage exists
        pruned_graph = 0
        tombstone_created = False
        upstream_ids: List[str] = []
        downstream_ids: List[str] = []

        if self.graph_store is not None:
            (
                pruned_graph,
                tombstone_created,
                upstream_ids,
                downstream_ids,
            ) = self.graph_store.purge_resource_with_ref_counting_and_tombstone(
                project_id=st.project_id,
                resource_id=st.dataset_id,
                applied_ttl_expression=st.effective_ttl_expression,
                purged_at_iso=ref_now.isoformat(),
            )

        if tombstone_created:
            self.repo.record_tombstone(
                LineageTombstoneContract(
                    project_id=st.project_id,
                    dataset_id=st.dataset_id,
                    tier=st.tier,
                    applied_ttl_expression=st.effective_ttl_expression,
                    purged_at=ref_now,
                    upstream_datasets=upstream_ids,
                    downstream_datasets=downstream_ids,
                    cleanup_run_id=run.run_id,
                )
            )
            run.tombstones_created += 1

        st.lifecycle_status = "PURGED"
        st.purged_at = ref_now
        st.last_error = None
        self.repo.upsert_dataset_state(st)

        run.datasets_purged += 1
        run.graph_elements_pruned += pruned_graph
        run.bytes_reclaimed += bytes_from_parts

    def _process_query_artifacts(
        self,
        project_id: Optional[str],
        run: CleanupJobRunContract,
        ref_now: datetime,
        dry_run: bool,
    ) -> None:
        artifacts = self.repo.list_query_artifacts(project_id=project_id)
        for art in artifacts:
            if art.lifecycle_status == "PURGED" or art.retention_hold or art.expires_at is None:
                continue
            exp = art.expires_at if art.expires_at.tzinfo else art.expires_at.replace(tzinfo=timezone.utc)
            if ref_now >= exp:
                run.query_artifacts_purged += 1
                run.bytes_reclaimed += art.size_bytes
                run.candidate_items.append(
                    {
                        "item_type": "QUERY_ARTIFACT",
                        "project_id": art.project_id,
                        "artifact_id": art.artifact_id,
                        "artifact_type": art.artifact_type,
                        "action": "PURGE",
                        "bytes_reclaimed": art.size_bytes,
                        "reason": f"Query artifact TTL ({art.ttl_expression}) elapsed",
                    }
                )
                if not dry_run:
                    self.repo.update_query_artifact_status(
                        artifact_id=art.artifact_id,
                        lifecycle_status="PURGED",
                        soft_deleted_at=ref_now,
                        purge_after=ref_now,
                    )

        # Also sweep the `ai_queries` query execution history table based on the active QUERY_HISTORY_LOG TTL policy (FR-003)
        try:
            history_policy = self.resolver.resolve_query_artifact_policy(
                project_id=project_id,
                artifact_type="QUERY_HISTORY_LOG",
            )
            if history_policy.ttl_seconds is not None and hasattr(self.repo, "purge_expired_query_history_logs"):
                history_cutoff = ref_now - timedelta(seconds=history_policy.ttl_seconds)
                logs_purged, log_bytes = self.repo.purge_expired_query_history_logs(
                    cutoff_utc=history_cutoff,
                    dry_run=dry_run,
                )
                if logs_purged > 0:
                    run.query_artifacts_purged += logs_purged
                    run.bytes_reclaimed += log_bytes
                    run.candidate_items.append(
                        {
                            "item_type": "QUERY_ARTIFACT",
                            "project_id": project_id,
                            "artifact_id": "ai_queries_history_table",
                            "artifact_type": "QUERY_HISTORY_LOG",
                            "action": "PURGE",
                            "bytes_reclaimed": log_bytes,
                            "reason": f"Purged {logs_purged} query history log entries older than {history_policy.ttl_expression}",
                        }
                    )
        except Exception as he:
            logger.debug(f"Query history log table sweep notice: {he}")
