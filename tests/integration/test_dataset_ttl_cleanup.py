from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
import pytest

from src.domains.retention.models.contract.retention import (
    DatasetTTLSetRequestContract,
    ProjectTTLDefaultsRequestContract,
    RetentionHoldRequestContract,
    DatasetRestoreRequestContract,
    CleanupTriggerRequestContract,
)
from src.domains.retention.operations.policy_resolver import PolicyResolver
from src.domains.retention.operations.query_interceptor import QueryTTLInterceptor
from src.domains.retention.operations.query_artifact_manager import QueryArtifactManager
from src.domains.retention.operations.parquet_compactor import (
    ParquetCompactor,
    extract_parquet_timestamp_bounds,
)
from src.domains.retention.operations.cleanup_engine import CleanupEngine
from src.domains.retention.facade.retention import RetentionFacade
from tests.unit.retention.test_policy_resolver import InMemoryRetentionRepository
from tests.unit.retention.test_parquet_compactor import FakeS3Storage, _build_parquet_bytes


class FakeQueryCache:
    """In-memory test double for Redis QueryCache with dataset dependency invalidation."""

    def __init__(self):
        self.store: Dict[str, str] = {}
        self.deps: Dict[str, set] = {}

    def set_sql(self, project_id, sql, payload_json, ttl=3600, source_datasets=None) -> str:
        key = f"artemis:sql:cache:{project_id}:{hash(sql)}"
        self.store[key] = payload_json
        for ds in (source_datasets or []):
            dep_key = f"{ds.get('project_id')}:{ds.get('dataset_id')}"
            self.deps.setdefault(dep_key, set()).add(key)
        return key

    def set(self, prompt, response, ttl=3600, source_datasets=None) -> str:
        key = f"artemis:ai:query:{hash(prompt)}"
        self.store[key] = response
        for ds in (source_datasets or []):
            dep_key = f"{ds.get('project_id')}:{ds.get('dataset_id')}"
            self.deps.setdefault(dep_key, set()).add(key)
        return key

    def invalidate_for_dataset(self, project_id: str, dataset_id: str) -> int:
        dep_key = f"{project_id}:{dataset_id}"
        keys = self.deps.pop(dep_key, set())
        for k in keys:
            self.store.pop(k, None)
        return len(keys)


class FakeKDGGraphStore:
    """In-memory test double for Memgraph reference-counted entity pruning and LineageTombstone conversion."""

    def __init__(self):
        # resource_id -> {"project_id": str, "status": str, "entities": set, "downstream": list, "upstream": list, "tombstone": bool}
        self.resources: Dict[Tuple[str, str], Dict] = {}

    def add_resource(self, project_id: str, resource_id: str, entities: List[str], downstream: Optional[List[str]] = None):
        self.resources[(project_id, resource_id)] = {
            "project_id": project_id,
            "resource_id": resource_id,
            "status": "ACTIVE",
            "entities": set(entities),
            "downstream": downstream or [],
            "upstream": [],
            "tombstone": False,
        }

    def set_resource_lifecycle_status(self, project_id: str, resource_id: str, lifecycle_status: str):
        if (project_id, resource_id) in self.resources:
            self.resources[(project_id, resource_id)]["status"] = lifecycle_status

    def get_active_project_entities(self, project_id: str) -> set:
        active_ents = set()
        for (pid, _), r in self.resources.items():
            if pid == project_id and r["status"] == "ACTIVE":
                active_ents.update(r["entities"])
        return active_ents

    def purge_resource_with_ref_counting_and_tombstone(
        self,
        project_id: str,
        resource_id: str,
        applied_ttl_expression: str,
        purged_at_iso: str,
    ) -> Tuple[int, bool, List[str], List[str]]:
        rec = self.resources.get((project_id, resource_id))
        if not rec:
            return 0, False, [], []

        own_entities = set(rec["entities"])
        rec["entities"] = set()
        rec["status"] = "PURGED"

        # Reference counting: check which of own_entities are still referenced by other active resources
        still_referenced = self.get_active_project_entities(project_id)
        orphaned_entities = own_entities - still_referenced
        pruned_count = len(orphaned_entities)

        downstream = list(rec["downstream"])
        upstream = list(rec["upstream"])
        if downstream or upstream:
            rec["tombstone"] = True
            rec["applied_ttl"] = applied_ttl_expression
            rec["purged_at"] = purged_at_iso
            return pruned_count, True, upstream, downstream
        else:
            self.resources.pop((project_id, resource_id), None)
            return pruned_count + 1, False, [], []


class AlwaysAllowMembership:
    def is_member(self, project_id: str, user_id: str, user_roles: list) -> bool:
        return project_id != "forbidden-proj"

    def is_owner(self, project_id: str, user_id: str, user_roles: list) -> bool:
        return user_id in ("admin", "owner")


@pytest.mark.asyncio
async def test_end_to_end_dataset_ttl_query_interception_and_two_stage_cleanup():
    repo = InMemoryRetentionRepository()
    fake_s3 = FakeS3Storage()
    fake_cache = FakeQueryCache()
    fake_graph = FakeKDGGraphStore()
    resolver = PolicyResolver(repository=repo)
    art_mgr = QueryArtifactManager(
        repository=repo,
        policy_resolver=resolver,
        query_cache=fake_cache,
        s3_storage=fake_s3,
    )
    compactor = ParquetCompactor(s3_storage=fake_s3)
    engine = CleanupEngine(
        repository=repo,
        policy_resolver=resolver,
        artifact_manager=art_mgr,
        parquet_compactor=compactor,
        s3_storage=fake_s3,
        graph_store=fake_graph,
    )
    facade = RetentionFacade(
        repository=repo,
        policy_resolver=resolver,
        artifact_manager=art_mgr,
        cleanup_engine=engine,
        membership_service=AlwaysAllowMembership(),
    )
    interceptor = QueryTTLInterceptor(repository=repo, policy_resolver=resolver)

    t0 = datetime(2026, 11, 1, 0, 0, 0, tzinfo=timezone.utc)

    # 1. Ingest two datasets in project 'alpha':
    #    - 'raw_telemetry' (upstream Bronze dataset with downstream Silver lineage 'curated_telemetry')
    #    - 'curated_telemetry' (Silver dataset sharing entity 'IP-10.0.0.1' with 'raw_telemetry')
    fake_s3.client.objects["projects/alpha/bronze/raw_telemetry/part1.parquet"] = b"PARQUET_RAW_BYTES_1000"
    fake_s3.client.objects["projects/alpha/silver/curated_telemetry/part1.parquet"] = b"PARQUET_SILVER_BYTES_500"

    fake_graph.add_resource(
        "alpha",
        "raw_telemetry",
        entities=["IP-10.0.0.1", "UNIQUE-BRONZE-ENTITY"],
        downstream=["curated_telemetry"],
    )
    fake_graph.add_resource(
        "alpha",
        "curated_telemetry",
        entities=["IP-10.0.0.1", "SILVER-ENTITY"],
        downstream=[],
    )

    st_raw = await facade.register_ingested_partition(
        project_id="alpha",
        dataset_id="raw_telemetry",
        tier="BRONZE",
        object_key="projects/alpha/bronze/raw_telemetry/part1.parquet",
        storage_uri="s3://telemetry/projects/alpha/bronze/raw_telemetry/part1.parquet",
        size_bytes=1000,
        record_count=50,
        ingested_at=t0,
        explicit_ttl_expression="2d",
    )
    assert st_raw.effective_ttl_expression == "2d"

    st_silver = await facade.register_ingested_partition(
        project_id="alpha",
        dataset_id="curated_telemetry",
        tier="SILVER",
        object_key="projects/alpha/silver/curated_telemetry/part1.parquet",
        storage_uri="s3://telemetry/projects/alpha/silver/curated_telemetry/part1.parquet",
        size_bytes=500,
        record_count=25,
        ingested_at=t0,
    )
    assert st_silver.effective_ttl_expression == "90d"
    assert st_silver.policy_source == "PLATFORM_DEFAULT"

    # 2. Register an ephemeral SQL cache entry (1h TTL) and a materialized query export (7d TTL)
    sql_art = art_mgr.register_sql_cache_entry(
        project_id="alpha",
        sql="SELECT * FROM raw_telemetry",
        result_payload={"rows": [[1]]},
        source_datasets=[{"project_id": "alpha", "dataset_id": "raw_telemetry", "tier": "BRONZE"}],
        explicit_ttl_expression="1h",
        now=t0,
    )
    exp_art = art_mgr.materialize_query_export(
        project_id="alpha",
        export_dataset_id="weekly_report",
        columns=["col1"],
        rows=[[1]],
        source_datasets=[{"project_id": "alpha", "dataset_id": "raw_telemetry", "tier": "BRONZE"}],
        explicit_ttl_expression="7d",
        now=t0,
    )
    assert sql_art.artifact_id in fake_cache.store
    assert repo.get_query_artifact("weekly_report").lifecycle_status == "ACTIVE"

    # 3. Advance time to t0 + 3 days (raw_telemetry 2d TTL has expired!)
    t_day3 = t0 + timedelta(days=3)

    # Verify read-time query interception immediately excludes raw_telemetry BEFORE background cleanup runs (SC-002)
    q_intercept = interceptor.intercept_sql_query(
        "SELECT * FROM read_parquet('s3://telemetry/projects/alpha/bronze/raw_telemetry/*.parquet')",
        now=t_day3,
    )
    assert q_intercept.short_circuit_empty is True

    # 4. Place an active query lease on raw_telemetry and verify cleanup safely skips locked datasets (FR-011, SC-004)
    lease_id = repo.acquire_lease("alpha", "raw_telemetry", "ANALYTICAL_QUERY", ttl_seconds=600)
    run_locked = await facade.trigger_cleanup(
        project_id="alpha",
        request=CleanupTriggerRequestContract(dry_run=False, include_query_artifacts=False),
        now=t_day3,
    )
    assert run_locked.skipped_locked_count == 1
    assert run_locked.datasets_soft_deleted == 0
    repo.release_lease(lease_id)

    # 5. Place a Retention Hold on raw_telemetry and verify cleanup skips held datasets (FR-010, SC-004)
    await facade.set_dataset_hold(
        "alpha",
        "raw_telemetry",
        RetentionHoldRequestContract(tier="BRONZE", retention_hold=True, reason="Audit hold"),
        now=t_day3,
    )
    run_held = await facade.trigger_cleanup(
        project_id="alpha",
        request=CleanupTriggerRequestContract(dry_run=False, include_query_artifacts=False),
        now=t_day3,
    )
    assert run_held.skipped_held_count == 1
    assert run_held.datasets_soft_deleted == 0

    # Release hold
    await facade.set_dataset_hold(
        "alpha",
        "raw_telemetry",
        RetentionHoldRequestContract(tier="BRONZE", retention_hold=False),
        now=t_day3,
    )

    # 6. Run Stage 1 Cleanup at t0 + 3d -> transitions raw_telemetry to SOFT_DELETED (24h grace period)
    #    and invalidates dependent ephemeral SQL cache while preserving weekly_report materialized export!
    run_stage1 = await facade.trigger_cleanup(
        project_id="alpha",
        request=CleanupTriggerRequestContract(dry_run=False, include_query_artifacts=False),
        now=t_day3,
    )
    assert run_stage1.datasets_soft_deleted == 1
    assert repo.get_dataset_state("alpha", "raw_telemetry", "BRONZE").lifecycle_status == "SOFT_DELETED"
    assert sql_art.artifact_id not in fake_cache.store
    assert repo.get_query_artifact(sql_art.artifact_id).lifecycle_status == "PURGED"
    assert repo.get_query_artifact("weekly_report").lifecycle_status == "ACTIVE"

    # 7. Test Explicit Restoration during grace period (at t0 + 3d + 6h)
    t_restore = t_day3 + timedelta(hours=6)
    restored = await facade.restore_dataset(
        "alpha",
        "raw_telemetry",
        DatasetRestoreRequestContract(tier="BRONZE", ttl_expression="10d"),
        now=t_restore,
    )
    assert restored.lifecycle_status == "ACTIVE"
    assert restored.effective_ttl_expression == "10d"

    # Set TTL back to 2d so it expires again and moves through Stage 1 -> Stage 2 Permanent Purge
    await facade.set_dataset_ttl(
        "alpha",
        "raw_telemetry",
        DatasetTTLSetRequestContract(tier="BRONZE", ttl_expression="2d", grace_period_expression="24h"),
        now=t_day3,
    )
    await facade.trigger_cleanup(
        project_id="alpha",
        request=CleanupTriggerRequestContract(dry_run=False, include_query_artifacts=False),
        now=t_day3,
    )
    assert repo.get_dataset_state("alpha", "raw_telemetry", "BRONZE").lifecycle_status == "SOFT_DELETED"

    # 8. Advance past 24h grace period (t0 + 4d + 2h):
    #    First run --dry-run preview and verify it predicts exact purge without deleting S3 files (FR-007, SC-005)
    t_day4 = t_day3 + timedelta(hours=26)
    dry_run_res = await facade.trigger_cleanup(
        project_id="alpha",
        request=CleanupTriggerRequestContract(dry_run=True, include_query_artifacts=False),
        now=t_day4,
    )
    assert dry_run_res.trigger_type == "DRY_RUN"
    assert dry_run_res.datasets_purged == 1
    assert dry_run_res.bytes_reclaimed == 1000
    assert "projects/alpha/bronze/raw_telemetry/part1.parquet" in fake_s3.client.objects

    # 9. Run Live Stage 2 Cleanup:
    #    - S3 object is deleted
    #    - Unshared entity 'UNIQUE-BRONZE-ENTITY' is pruned from Memgraph
    #    - Shared entity 'IP-10.0.0.1' (also in curated_telemetry) is preserved!
    #    - Because raw_telemetry has downstream lineage to curated_telemetry, a LineageTombstone is created!
    live_purge_res = await facade.trigger_cleanup(
        project_id="alpha",
        request=CleanupTriggerRequestContract(dry_run=False, include_query_artifacts=False),
        now=t_day4,
    )
    assert live_purge_res.datasets_purged == 1
    assert live_purge_res.bytes_reclaimed == 1000
    assert live_purge_res.tombstones_created == 1
    assert live_purge_res.graph_elements_pruned == 1
    assert "projects/alpha/bronze/raw_telemetry/part1.parquet" not in fake_s3.client.objects
    assert "IP-10.0.0.1" in fake_graph.get_active_project_entities("alpha")
    assert "UNIQUE-BRONZE-ENTITY" not in fake_graph.get_active_project_entities("alpha")
    assert fake_graph.resources[("alpha", "raw_telemetry")]["tombstone"] is True

    tombstones = repo.list_tombstones("alpha")
    assert len(tombstones) == 1
    assert tombstones[0].dataset_id == "raw_telemetry"
    assert tombstones[0].downstream_datasets == ["curated_telemetry"]

    # 10. Verify QUERY_HISTORY_LOG table sweep (FR-003 / T045)
    repo.query_history_logs = [
        {"query_id": "q-old", "created_at": t0 - timedelta(days=40), "bytes": 512},
        {"query_id": "q-recent", "created_at": t_day4 - timedelta(days=1), "bytes": 256},
    ]
    history_run = await facade.trigger_cleanup(
        project_id="alpha",
        request=CleanupTriggerRequestContract(dry_run=False, include_query_artifacts=True),
        now=t_day4,
    )
    assert history_run.query_artifacts_purged >= 1
    assert len(repo.query_history_logs) == 1
    assert repo.query_history_logs[0]["query_id"] == "q-recent"


@pytest.mark.asyncio
async def test_end_to_end_timestamp_column_row_compaction_lifecycle():
    repo = InMemoryRetentionRepository()
    fake_s3 = FakeS3Storage()
    resolver = PolicyResolver(repository=repo)
    compactor = ParquetCompactor(s3_storage=fake_s3)
    engine = CleanupEngine(
        repository=repo,
        policy_resolver=resolver,
        parquet_compactor=compactor,
        s3_storage=fake_s3,
    )
    facade = RetentionFacade(
        repository=repo,
        policy_resolver=resolver,
        cleanup_engine=engine,
        membership_service=AlwaysAllowMembership(),
    )
    interceptor = QueryTTLInterceptor(repository=repo, policy_resolver=resolver)

    raw_bytes, table = _build_parquet_bytes(
        [
            "2026-11-01T00:00:00Z",  # Old row
            "2026-11-09T00:00:00Z",  # Fresh row
            "2026-11-10T00:00:00Z",  # Fresh row
        ]
    )
    obj_key = "projects/alpha/bronze/stream_events/batch1.parquet"
    fake_s3.client.objects[obj_key] = raw_bytes
    min_ts, max_ts = extract_parquet_timestamp_bounds(table, "event_ts")

    t_ingest = datetime(2026, 11, 10, 0, 0, 0, tzinfo=timezone.utc)
    await facade.register_ingested_partition(
        project_id="alpha",
        dataset_id="stream_events",
        tier="BRONZE",
        object_key=obj_key,
        storage_uri=f"s3://telemetry/{obj_key}",
        size_bytes=len(raw_bytes),
        record_count=3,
        ingested_at=t_ingest,
        min_event_ts=min_ts,
        max_event_ts=max_ts,
        explicit_ttl_expression="7d",
        timestamp_column="event_ts",
    )

    # 1. Read-time query interception at Nov 10 injects `event_ts >= 2026-11-03T00:00:00Z`
    q_res = interceptor.intercept_sql_query(
        "SELECT * FROM read_parquet('s3://telemetry/projects/alpha/bronze/stream_events/*.parquet')",
        now=t_ingest,
    )
    assert 'TRY_CAST("event_ts" AS TIMESTAMPTZ) >= TIMESTAMPTZ \'2026-11-03T00:00:00Z\'' in q_res.rewritten_sql

    # 2. Cleanup at Nov 10: row 1 (Nov 1) is older than TTL (7d) + grace (24h = 8d total, cutoff Nov 2) -> compacts file!
    cleanup_res = await facade.trigger_cleanup(
        project_id="alpha",
        request=CleanupTriggerRequestContract(dry_run=False, include_query_artifacts=False),
        now=t_ingest,
    )
    assert cleanup_res.partitions_compacted == 1
    assert cleanup_res.rows_pruned == 1
    parts = repo.list_partitions("alpha", "stream_events", "BRONZE")
    assert len(parts) == 1
    assert parts[0].record_count == 2
    assert parts[0].min_event_ts == datetime(2026, 11, 9, 0, 0, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_live_containers_end_to_end_ttl_ingestion_query_and_cleanup():
    """
    Live end-to-end integration test executing against the running PostgreSQL, MinIO, DuckDB,
    Memgraph, and Redis containers to validate the complete quickstart lifecycle.
    """
    import uuid
    from src.domains.project.facade.project import ProjectFacade
    from src.domains.project.models.contract.project import ProjectCreateContract
    from src.domains.analytics.operations.project_query import ProjectQueryExecutor
    from src.domains.discovery.facade.discovery import DiscoveryFacade

    proj_id = f"test-ttl-live-{uuid.uuid4().hex[:8]}"
    project_facade = ProjectFacade()
    retention_facade = RetentionFacade()
    discovery_facade = DiscoveryFacade()
    query_executor = ProjectQueryExecutor()

    try:
        # 1. Create live project workspace in PostgreSQL
        await project_facade.create_project(
            ProjectCreateContract(project_id=proj_id, name="Live TTL Integration Project"),
            creator_user_id="admin",
        )

        # 2. Ingest live CSV dataset into MinIO Bronze with explicit 30d TTL
        csv_bytes = (
            b"device_id,metric_name,value,event_ts\n"
            b"dev-1,cpu_load,88.5,2026-11-20T10:00:00Z\n"
            b"dev-2,cpu_load,42.0,2026-11-21T10:00:00Z\n"
        )
        ingest_res = await project_facade.ingest_tabular(
            project_id=proj_id,
            dataset_name="live_sensors",
            data_bytes=csv_bytes,
            filename="live_sensors.csv",
            tier="BRONZE",
            ttl_expression="30d",
        )
        assert ingest_res.records_ingested == 2
        assert ingest_res.effective_ttl_expression == "30d"

        # 3. Inspect persisted TTL state from live PostgreSQL
        state = await retention_facade.get_dataset_ttl(proj_id, "live_sensors", tier="BRONZE")
        assert state.effective_ttl_expression == "30d"
        assert state.policy_source == "DATASET_EXPLICIT"
        assert state.active_partitions_count == 1

        # 4. Execute live DuckDB query over MinIO Parquet with cache_ttl and materialized export_dataset
        q_sql = f"SELECT device_id, value FROM read_parquet('s3://telemetry/projects/{proj_id}/bronze/live_sensors/**/*.parquet') ORDER BY device_id"
        q_res = query_executor.execute_scoped_query(
            project_id=proj_id,
            sql=q_sql,
            cache_ttl="15m",
            export_dataset="live_sensors_export",
            export_ttl="2d",
        )
        assert q_res["row_count"] == 2
        assert q_res.get("cache_ttl") == "15m"
        assert q_res.get("export_artifact_id") == "live_sensors_export"

        # 5. Simulate dataset expiration in live PostgreSQL and verify immediate read-time DuckDB exclusion (SC-002)
        past_now = datetime.now(timezone.utc) + timedelta(days=35)
        cleanup_dry = await retention_facade.trigger_cleanup(
            project_id=proj_id,
            request=CleanupTriggerRequestContract(dry_run=True),
            now=past_now,
        )
        assert cleanup_dry.trigger_type == "DRY_RUN"
        assert cleanup_dry.datasets_soft_deleted == 1

        # Stage 1 live cleanup -> moves dataset to SOFT_DELETED
        cleanup_stage1 = await retention_facade.trigger_cleanup(
            project_id=proj_id,
            request=CleanupTriggerRequestContract(dry_run=False),
            now=past_now,
        )
        assert cleanup_stage1.datasets_soft_deleted == 1

        # Querying the soft-deleted dataset via live ProjectQueryExecutor returns 0 rows immediately
        q_after_soft_delete = query_executor.execute_scoped_query(project_id=proj_id, sql=q_sql)
        assert q_after_soft_delete["row_count"] == 0
        assert q_after_soft_delete.get("ttl_filtered") is True

        # 6. Restore soft-deleted dataset in live PostgreSQL/Memgraph and verify query returns 2 rows again!
        restored = await retention_facade.restore_dataset(
            project_id=proj_id,
            dataset_id="live_sensors",
            request=DatasetRestoreRequestContract(tier="BRONZE", ttl_expression="60d"),
            now=past_now + timedelta(hours=1),
        )
        assert restored.lifecycle_status == "ACTIVE"

        q_after_restore = query_executor.execute_scoped_query(project_id=proj_id, sql=q_sql)
        assert q_after_restore["row_count"] == 2

        # 7. Set 0h grace period and trigger permanent purge across MinIO, Memgraph, Redis, and PostgreSQL
        await retention_facade.set_dataset_ttl(
            project_id=proj_id,
            dataset_id="live_sensors",
            request=DatasetTTLSetRequestContract(tier="BRONZE", ttl_expression="1d", grace_period_expression="0h"),
            now=past_now,
        )
        purge_run = await retention_facade.trigger_cleanup(
            project_id=proj_id,
            request=CleanupTriggerRequestContract(dry_run=False),
            now=past_now + timedelta(days=2),
        )
        assert purge_run.datasets_purged == 1
        assert purge_run.bytes_reclaimed > 0

        final_state = await retention_facade.get_dataset_ttl(proj_id, "live_sensors", tier="BRONZE")
        assert final_state.lifecycle_status == "PURGED"

        runs = await retention_facade.list_cleanup_runs(project_id=proj_id)
        assert len(runs) >= 3
    finally:
        await project_facade.delete_project(proj_id)
