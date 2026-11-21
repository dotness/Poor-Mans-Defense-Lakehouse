import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
import pytest

from src.domains.retention.models.contract.retention import (
    TTLPolicyContract,
    DatasetTTLSetRequestContract,
    ProjectTTLDefaultsRequestContract,
    DatasetRetentionStateContract,
    DatasetPartitionContract,
    QueryDataArtifactContract,
    RetentionHoldRequestContract,
    DatasetRestoreRequestContract,
    CleanupJobRunContract,
    LineageTombstoneContract,
)
from src.domains.retention.operations.policy_resolver import PolicyResolver


class InMemoryRetentionRepository:
    """In-memory test double for RetentionRepository."""

    def __init__(self):
        self.policies: Dict[str, TTLPolicyContract] = {}
        self.states: Dict[str, DatasetRetentionStateContract] = {}
        self.partitions: List[DatasetPartitionContract] = []
        self.query_artifacts: Dict[str, QueryDataArtifactContract] = {}
        self.tombstones: List[LineageTombstoneContract] = []
        self.cleanup_runs: List[CleanupJobRunContract] = []
        self.leases: Dict[str, Dict[str, Any]] = {}

    def _policy_key(self, project_id, target_scope, tier=None, dataset_id=None, query_artifact_type=None) -> str:
        return f"{project_id or '__GLOBAL__'}:{target_scope}:{tier or ''}:{dataset_id or ''}:{query_artifact_type or ''}"

    def upsert_policy(self, policy: TTLPolicyContract) -> TTLPolicyContract:
        key = self._policy_key(
            policy.project_id,
            policy.target_scope,
            policy.tier,
            policy.dataset_id,
            policy.query_artifact_type,
        )
        if not policy.policy_id:
            policy.policy_id = str(uuid.uuid4())
        self.policies[key] = policy
        return policy

    def get_policy(self, project_id, target_scope, tier=None, dataset_id=None, query_artifact_type=None):
        key = self._policy_key(project_id, target_scope, tier, dataset_id, query_artifact_type)
        return self.policies.get(key)

    def delete_dataset_policy(self, project_id: str, dataset_id: str, tier: str) -> bool:
        key = self._policy_key(project_id, "DATASET", tier.upper(), dataset_id, None)
        return self.policies.pop(key, None) is not None

    def add_partition(
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
    ) -> DatasetPartitionContract:
        tier_up = tier.upper()
        if overwrite:
            self.partitions = [
                p for p in self.partitions if not (p.project_id == project_id and p.dataset_id == dataset_id and p.tier == tier_up)
            ]
        part = DatasetPartitionContract(
            partition_id=str(uuid.uuid4()),
            project_id=project_id,
            dataset_id=dataset_id,
            tier=tier_up,
            object_key=object_key,
            storage_uri=storage_uri,
            size_bytes=size_bytes,
            record_count=record_count,
            ingested_at=ingested_at or datetime.now(timezone.utc),
            min_event_ts=min_event_ts,
            max_event_ts=max_event_ts,
            lifecycle_status="ACTIVE",
        )
        self.partitions.append(part)
        return part

    def list_partitions(self, project_id: str, dataset_id=None, tier=None, lifecycle_status=None):
        res = [p for p in self.partitions if p.project_id == project_id]
        if dataset_id:
            res = [p for p in res if p.dataset_id == dataset_id]
        if tier:
            res = [p for p in res if p.tier == tier.upper()]
        if lifecycle_status:
            res = [p for p in res if p.lifecycle_status == lifecycle_status]
        return sorted(res, key=lambda x: x.ingested_at)

    def update_partition_status(self, partition_id: str, lifecycle_status: str, soft_deleted_at=None):
        for p in self.partitions:
            if p.partition_id == partition_id:
                p.lifecycle_status = lifecycle_status
                p.soft_deleted_at = soft_deleted_at

    def update_compacted_partition(self, partition_id, new_object_key, new_storage_uri, new_size_bytes, new_record_count, new_min_event_ts, new_max_event_ts):
        for p in self.partitions:
            if p.partition_id == partition_id:
                p.object_key = new_object_key
                p.storage_uri = new_storage_uri
                p.size_bytes = new_size_bytes
                p.record_count = new_record_count
                p.min_event_ts = new_min_event_ts
                p.max_event_ts = new_max_event_ts

    def upsert_dataset_state(self, state: DatasetRetentionStateContract) -> DatasetRetentionStateContract:
        key = f"{state.project_id}:{state.dataset_id}:{state.tier.upper()}"
        self.states[key] = state.model_copy(deep=True)
        return self.states[key]

    def get_dataset_state(self, project_id: str, dataset_id: str, tier: str = "BRONZE"):
        key = f"{project_id}:{dataset_id}:{tier.upper()}"
        st = self.states.get(key)
        return st.model_copy(deep=True) if st else None

    def list_dataset_states(self, project_id: Optional[str] = None):
        vals = list(self.states.values())
        if project_id:
            vals = [v for v in vals if v.project_id == project_id]
        return [v.model_copy(deep=True) for v in vals]

    def upsert_query_artifact(self, artifact: QueryDataArtifactContract):
        self.query_artifacts[artifact.artifact_id] = artifact.model_copy(deep=True)
        return self.query_artifacts[artifact.artifact_id]

    def get_query_artifact(self, artifact_id: str):
        art = self.query_artifacts.get(artifact_id)
        return art.model_copy(deep=True) if art else None

    def list_query_artifacts(self, project_id=None, artifact_type=None, lifecycle_status=None):
        res = list(self.query_artifacts.values())
        if project_id is not None:
            res = [a for a in res if a.project_id == project_id]
        if artifact_type is not None:
            res = [a for a in res if a.artifact_type == artifact_type]
        if lifecycle_status is not None:
            res = [a for a in res if a.lifecycle_status == lifecycle_status]
        return res

    def update_query_artifact_status(self, artifact_id, lifecycle_status, soft_deleted_at=None, purge_after=None):
        if artifact_id in self.query_artifacts:
            self.query_artifacts[artifact_id].lifecycle_status = lifecycle_status
            self.query_artifacts[artifact_id].soft_deleted_at = soft_deleted_at
            self.query_artifacts[artifact_id].purge_after = purge_after

    def purge_expired_query_history_logs(self, cutoff_utc: datetime, dry_run: bool = False):
        history_logs = getattr(self, "query_history_logs", [])
        expired = [row for row in history_logs if row["created_at"] <= cutoff_utc]
        total_bytes = sum(int(row.get("bytes", 128)) for row in expired)
        if not dry_run:
            self.query_history_logs = [row for row in history_logs if row["created_at"] > cutoff_utc]
        return len(expired), total_bytes

    def acquire_lease(self, project_id, dataset_id, operation_type, holder_id=None, ttl_seconds=300) -> str:
        lid = str(uuid.uuid4())
        self.leases[lid] = {
            "project_id": project_id,
            "dataset_id": dataset_id,
            "operation_type": operation_type,
            "expires_at": datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds),
        }
        return lid

    def release_lease(self, lease_id: str):
        self.leases.pop(lease_id, None)

    def has_active_lease(self, project_id: str, dataset_id: str, now: Optional[datetime] = None) -> bool:
        ref = now or datetime.now(timezone.utc)
        for l in self.leases.values():
            if l["project_id"] == project_id and l["dataset_id"] in (dataset_id, "*") and l["expires_at"] > ref:
                return True
        return False

    def cleanup_expired_leases(self, now: Optional[datetime] = None) -> int:
        ref = now or datetime.now(timezone.utc)
        expired = [k for k, v in self.leases.items() if v["expires_at"] <= ref]
        for k in expired:
            self.leases.pop(k, None)
        return len(expired)

    def record_cleanup_run(self, run: CleanupJobRunContract) -> CleanupJobRunContract:
        self.cleanup_runs = [r for r in self.cleanup_runs if r.run_id != run.run_id]
        self.cleanup_runs.insert(0, run.model_copy(deep=True))
        return run

    def list_cleanup_runs(self, project_id=None, limit=20):
        res = self.cleanup_runs
        if project_id:
            res = [r for r in res if r.project_id == project_id]
        return res[:limit]

    def record_tombstone(self, tombstone: LineageTombstoneContract):
        self.tombstones = [
            t for t in self.tombstones if not (t.project_id == tombstone.project_id and t.dataset_id == tombstone.dataset_id and t.tier == tombstone.tier)
        ]
        self.tombstones.append(tombstone)
        return tombstone

    def list_tombstones(self, project_id: str):
        return [t for t in self.tombstones if t.project_id == project_id]


def test_policy_hierarchy_resolution():
    repo = InMemoryRetentionRepository()
    resolver = PolicyResolver(repository=repo)

    # 1. Platform default when no policies set
    p, src = resolver.resolve_effective_dataset_policy("proj-a", "logs", "BRONZE")
    assert src == "PLATFORM_DEFAULT"
    assert p.ttl_expression == "30d"

    p_silver, src_silver = resolver.resolve_effective_dataset_policy("proj-a", "clean_logs", "SILVER")
    assert src_silver == "PLATFORM_DEFAULT"
    assert p_silver.ttl_expression == "90d"

    # 2. Project default overrides platform default
    resolver.set_default_ttl(
        "proj-a",
        ProjectTTLDefaultsRequestContract(target_scope="PROJECT", ttl_expression="60d"),
    )
    p, src = resolver.resolve_effective_dataset_policy("proj-a", "logs", "BRONZE")
    assert src == "PROJECT_DEFAULT"
    assert p.ttl_expression == "60d"

    # 3. Tier default overrides project default
    resolver.set_default_ttl(
        "proj-a",
        ProjectTTLDefaultsRequestContract(target_scope="TIER", tier="BRONZE", ttl_expression="14d"),
    )
    p, src = resolver.resolve_effective_dataset_policy("proj-a", "logs", "BRONZE")
    assert src == "TIER_DEFAULT"
    assert p.ttl_expression == "14d"

    # 4. Dataset explicit overrides tier default
    state = resolver.set_dataset_ttl(
        "proj-a",
        "logs",
        DatasetTTLSetRequestContract(tier="BRONZE", ttl_expression="7d"),
    )
    assert state.policy_source == "DATASET_EXPLICIT"
    assert state.effective_ttl_expression == "7d"

    # 5. Clearing dataset explicit policy reverts to tier default (14d)
    cleared = resolver.clear_dataset_ttl("proj-a", "logs", "BRONZE")
    assert cleared.policy_source == "TIER_DEFAULT"
    assert cleared.effective_ttl_expression == "14d"


def test_append_vs_overwrite_partition_clocks():
    repo = InMemoryRetentionRepository()
    resolver = PolicyResolver(repository=repo)
    base_time = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc)

    # First file ingested at base_time
    repo.add_partition(
        project_id="proj-a",
        dataset_id="stream",
        tier="BRONZE",
        object_key="part1.parquet",
        storage_uri="s3://telemetry/part1.parquet",
        size_bytes=1024,
        record_count=100,
        ingested_at=base_time,
        overwrite=False,
    )
    st1 = resolver.compute_and_persist_dataset_state("proj-a", "stream", "BRONZE", now=base_time + timedelta(days=5))
    assert st1.reference_timestamp == base_time
    assert st1.active_partitions_count == 1

    # Appending second file 5 days later keeps earliest active partition as reference_timestamp
    append_time = base_time + timedelta(days=5)
    repo.add_partition(
        project_id="proj-a",
        dataset_id="stream",
        tier="BRONZE",
        object_key="part2.parquet",
        storage_uri="s3://telemetry/part2.parquet",
        size_bytes=2048,
        record_count=200,
        ingested_at=append_time,
        overwrite=False,
    )
    st2 = resolver.compute_and_persist_dataset_state("proj-a", "stream", "BRONZE", now=append_time)
    assert st2.reference_timestamp == base_time
    assert st2.active_partitions_count == 2
    assert len(repo.list_partitions("proj-a", "stream", "BRONZE")) == 2

    # Overwriting the dataset resets partitions and shifts reference_timestamp to overwrite_time
    overwrite_time = base_time + timedelta(days=10)
    repo.add_partition(
        project_id="proj-a",
        dataset_id="stream",
        tier="BRONZE",
        object_key="part3.parquet",
        storage_uri="s3://telemetry/part3.parquet",
        size_bytes=4096,
        record_count=400,
        ingested_at=overwrite_time,
        overwrite=True,
    )
    st3 = resolver.compute_and_persist_dataset_state("proj-a", "stream", "BRONZE", now=overwrite_time)
    assert st3.reference_timestamp == overwrite_time
    assert st3.active_partitions_count == 1


def test_explicit_and_implicit_restoration_and_holds():
    repo = InMemoryRetentionRepository()
    resolver = PolicyResolver(repository=repo)
    t0 = datetime(2026, 11, 1, 0, 0, 0, tzinfo=timezone.utc)

    repo.add_partition(
        project_id="proj-a",
        dataset_id="ds1",
        tier="BRONZE",
        object_key="p1.parquet",
        storage_uri="s3://telemetry/p1.parquet",
        size_bytes=500,
        record_count=50,
        ingested_at=t0,
    )
    state = resolver.set_dataset_ttl(
        "proj-a",
        "ds1",
        DatasetTTLSetRequestContract(tier="BRONZE", ttl_expression="1d", grace_period_expression="24h"),
        now=t0,
    )
    assert state.lifecycle_status == "EXPIRING_SOON"

    # Simulate transition to SOFT_DELETED at t0 + 25h
    t_soft = t0 + timedelta(hours=25)
    state.lifecycle_status = "SOFT_DELETED"
    state.soft_deleted_at = t_soft
    state.purge_after = t_soft + timedelta(hours=24)
    repo.upsert_dataset_state(state)
    for p in repo.list_partitions("proj-a", "ds1", "BRONZE"):
        repo.update_partition_status(p.partition_id, "SOFT_DELETED", t_soft)

    # 1. Implicit restore by updating TTL to 30d
    restored_implicit = resolver.set_dataset_ttl(
        "proj-a",
        "ds1",
        DatasetTTLSetRequestContract(tier="BRONZE", ttl_expression="30d"),
        now=t_soft + timedelta(hours=2),
    )
    assert restored_implicit.lifecycle_status == "ACTIVE"
    assert restored_implicit.auto_restored is True
    assert restored_implicit.soft_deleted_at is None
    assert repo.list_partitions("proj-a", "ds1", "BRONZE")[0].lifecycle_status == "ACTIVE"

    # Move back to SOFT_DELETED and test implicit restore via Retention Hold
    restored_implicit.lifecycle_status = "SOFT_DELETED"
    restored_implicit.soft_deleted_at = t_soft
    repo.upsert_dataset_state(restored_implicit)

    held = resolver.set_dataset_hold(
        "proj-a",
        "ds1",
        RetentionHoldRequestContract(tier="BRONZE", retention_hold=True, reason="Legal review"),
        now=t_soft + timedelta(hours=3),
    )
    assert held.lifecycle_status == "HELD"
    assert held.retention_hold is True
    assert held.auto_restored is True

    # Release hold
    unheld = resolver.set_dataset_hold(
        "proj-a",
        "ds1",
        RetentionHoldRequestContract(tier="BRONZE", retention_hold=False),
        now=t_soft + timedelta(hours=3),
    )
    assert unheld.lifecycle_status == "ACTIVE"
    assert unheld.retention_hold is False

    # Move to SOFT_DELETED and test explicit restore command
    unheld.lifecycle_status = "SOFT_DELETED"
    unheld.soft_deleted_at = t_soft
    repo.upsert_dataset_state(unheld)

    explicit_restored = resolver.restore_soft_deleted_dataset(
        "proj-a",
        "ds1",
        DatasetRestoreRequestContract(tier="BRONZE", ttl_expression="60d"),
        now=t_soft + timedelta(hours=4),
    )
    assert explicit_restored.lifecycle_status == "ACTIVE"
    assert explicit_restored.effective_ttl_expression == "60d"

    # Attempting to restore a PURGED dataset raises LookupError (maps to HTTP 409)
    explicit_restored.lifecycle_status = "PURGED"
    repo.upsert_dataset_state(explicit_restored)
    with pytest.raises(LookupError, match="already been permanently PURGED"):
        resolver.restore_soft_deleted_dataset(
            "proj-a",
            "ds1",
            DatasetRestoreRequestContract(tier="BRONZE", ttl_expression="90d"),
            now=t_soft + timedelta(hours=5),
        )
