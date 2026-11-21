import json
import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
import psycopg2
from psycopg2.extras import RealDictCursor

try:
    from src.config.settings import settings
except ImportError:
    from config.settings import settings

from src.domains.retention.models.contract.retention import (
    TTLPolicyContract,
    DatasetRetentionStateContract,
    DatasetPartitionContract,
    QueryDataArtifactContract,
    CleanupJobRunContract,
    LineageTombstoneContract,
)

logger = logging.getLogger("artemis.retention.repository")


class RetentionRepository:
    """Manages PostgreSQL persistence for TTL policies, dataset states, partitions, leases, query artifacts, cleanup runs, and tombstones."""

    _schema_verified: bool = False

    def __init__(self):
        self.host = settings.postgres_host
        self.port = settings.postgres_port
        self.dbname = settings.postgres_db
        self.user = settings.postgres_user
        self.password = settings.postgres_password
        self._ensure_schema()

    def _get_connection(self):
        return psycopg2.connect(
            host=self.host,
            port=self.port,
            dbname=self.dbname,
            user=self.user,
            password=self.password,
            cursor_factory=RealDictCursor,
        )

    def _ensure_schema(self) -> None:
        """Auto-bootstraps the Feature 009 tables if not already initialized in PostgreSQL."""
        if RetentionRepository._schema_verified:
            return
        ddl = """
        CREATE TABLE IF NOT EXISTS ttl_policies (
            policy_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id VARCHAR(64) REFERENCES projects(project_id) ON DELETE CASCADE,
            target_scope VARCHAR(32) NOT NULL,
            tier VARCHAR(32),
            dataset_id VARCHAR(128),
            query_artifact_type VARCHAR(32),
            ttl_expression VARCHAR(32) NOT NULL,
            ttl_seconds BIGINT,
            granularity VARCHAR(32) NOT NULL DEFAULT 'INGESTION_AGE',
            timestamp_column VARCHAR(128),
            grace_period_expression VARCHAR(32) NOT NULL DEFAULT '24h',
            grace_period_seconds BIGINT NOT NULL DEFAULT 86400,
            updated_by VARCHAR(64) NOT NULL DEFAULT 'admin',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );

        CREATE UNIQUE INDEX IF NOT EXISTS uq_ttl_policies_scope ON ttl_policies (
            COALESCE(project_id, '__GLOBAL__'),
            target_scope,
            COALESCE(tier, ''),
            COALESCE(dataset_id, ''),
            COALESCE(query_artifact_type, '')
        );

        CREATE TABLE IF NOT EXISTS dataset_retention_states (
            project_id VARCHAR(64) NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
            dataset_id VARCHAR(128) NOT NULL,
            tier VARCHAR(32) NOT NULL DEFAULT 'BRONZE',
            effective_policy_id UUID REFERENCES ttl_policies(policy_id) ON DELETE SET NULL,
            policy_source VARCHAR(32) NOT NULL DEFAULT 'TIER_DEFAULT',
            effective_ttl_expression VARCHAR(32) NOT NULL DEFAULT '30d',
            effective_ttl_seconds BIGINT,
            granularity VARCHAR(32) NOT NULL DEFAULT 'INGESTION_AGE',
            timestamp_column VARCHAR(128),
            grace_period_expression VARCHAR(32) NOT NULL DEFAULT '24h',
            grace_period_seconds BIGINT NOT NULL DEFAULT 86400,
            reference_timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP WITH TIME ZONE,
            soft_deleted_at TIMESTAMP WITH TIME ZONE,
            purge_after TIMESTAMP WITH TIME ZONE,
            purged_at TIMESTAMP WITH TIME ZONE,
            retention_hold BOOLEAN NOT NULL DEFAULT FALSE,
            hold_reason TEXT,
            held_by VARCHAR(64),
            lifecycle_status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE',
            last_error TEXT,
            last_evaluated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (project_id, dataset_id, tier)
        );

        CREATE TABLE IF NOT EXISTS dataset_partitions (
            partition_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id VARCHAR(64) NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
            dataset_id VARCHAR(128) NOT NULL,
            tier VARCHAR(32) NOT NULL DEFAULT 'BRONZE',
            object_key TEXT NOT NULL,
            storage_uri TEXT NOT NULL,
            size_bytes BIGINT NOT NULL DEFAULT 0,
            record_count BIGINT NOT NULL DEFAULT 0,
            ingested_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            min_event_ts TIMESTAMP WITH TIME ZONE,
            max_event_ts TIMESTAMP WITH TIME ZONE,
            lifecycle_status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE',
            soft_deleted_at TIMESTAMP WITH TIME ZONE
        );

        CREATE TABLE IF NOT EXISTS query_data_artifacts (
            artifact_id VARCHAR(128) PRIMARY KEY,
            project_id VARCHAR(64) REFERENCES projects(project_id) ON DELETE CASCADE,
            artifact_type VARCHAR(32) NOT NULL,
            storage_uri TEXT NOT NULL,
            source_datasets JSONB NOT NULL DEFAULT '[]'::jsonb,
            size_bytes BIGINT NOT NULL DEFAULT 0,
            ttl_expression VARCHAR(32) NOT NULL,
            ttl_seconds BIGINT,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP WITH TIME ZONE,
            soft_deleted_at TIMESTAMP WITH TIME ZONE,
            purge_after TIMESTAMP WITH TIME ZONE,
            retention_hold BOOLEAN NOT NULL DEFAULT FALSE,
            lifecycle_status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE'
        );

        CREATE TABLE IF NOT EXISTS dataset_active_leases (
            lease_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id VARCHAR(64) NOT NULL,
            dataset_id VARCHAR(128) NOT NULL,
            operation_type VARCHAR(32) NOT NULL,
            holder_id VARCHAR(128) NOT NULL,
            acquired_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP WITH TIME ZONE NOT NULL
        );

        CREATE TABLE IF NOT EXISTS cleanup_job_runs (
            run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            trigger_type VARCHAR(32) NOT NULL,
            project_id VARCHAR(64),
            initiated_by VARCHAR(64) NOT NULL DEFAULT 'system',
            status VARCHAR(32) NOT NULL DEFAULT 'RUNNING',
            datasets_evaluated INTEGER NOT NULL DEFAULT 0,
            datasets_soft_deleted INTEGER NOT NULL DEFAULT 0,
            datasets_purged INTEGER NOT NULL DEFAULT 0,
            partitions_compacted INTEGER NOT NULL DEFAULT 0,
            rows_pruned BIGINT NOT NULL DEFAULT 0,
            query_artifacts_purged INTEGER NOT NULL DEFAULT 0,
            graph_elements_pruned INTEGER NOT NULL DEFAULT 0,
            tombstones_created INTEGER NOT NULL DEFAULT 0,
            bytes_reclaimed BIGINT NOT NULL DEFAULT 0,
            skipped_held_count INTEGER NOT NULL DEFAULT 0,
            skipped_locked_count INTEGER NOT NULL DEFAULT 0,
            candidate_items JSONB NOT NULL DEFAULT '[]'::jsonb,
            errors JSONB NOT NULL DEFAULT '[]'::jsonb,
            started_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP WITH TIME ZONE,
            duration_ms INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS lineage_tombstones (
            project_id VARCHAR(64) NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
            dataset_id VARCHAR(128) NOT NULL,
            tier VARCHAR(32) NOT NULL,
            applied_ttl_expression VARCHAR(32) NOT NULL,
            purged_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            upstream_datasets JSONB NOT NULL DEFAULT '[]'::jsonb,
            downstream_datasets JSONB NOT NULL DEFAULT '[]'::jsonb,
            cleanup_run_id UUID REFERENCES cleanup_job_runs(run_id) ON DELETE SET NULL,
            PRIMARY KEY (project_id, dataset_id, tier)
        );
        """
        try:
            conn = self._get_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute(ddl)
                    conn.commit()
                RetentionRepository._schema_verified = True
            finally:
                conn.close()
        except Exception as e:
            logger.debug(f"RetentionRepository schema bootstrap deferred: {e}")

    # ------------------------------------------------------------------
    # TTL Policies CRUD
    # ------------------------------------------------------------------
    def upsert_policy(self, policy: TTLPolicyContract) -> TTLPolicyContract:
        """Inserts or updates a TTL policy by scope."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                # Look up existing matching scope row
                find_sql = """
                    SELECT policy_id FROM ttl_policies
                    WHERE COALESCE(project_id, '__GLOBAL__') = COALESCE(%s, '__GLOBAL__')
                      AND target_scope = %s
                      AND COALESCE(tier, '') = COALESCE(%s, '')
                      AND COALESCE(dataset_id, '') = COALESCE(%s, '')
                      AND COALESCE(query_artifact_type, '') = COALESCE(%s, '');
                """
                cur.execute(
                    find_sql,
                    (
                        policy.project_id,
                        policy.target_scope,
                        policy.tier,
                        policy.dataset_id,
                        policy.query_artifact_type,
                    ),
                )
                existing = cur.fetchone()
                if existing:
                    update_sql = """
                        UPDATE ttl_policies
                        SET ttl_expression = %s,
                            ttl_seconds = %s,
                            granularity = %s,
                            timestamp_column = %s,
                            grace_period_expression = %s,
                            grace_period_seconds = %s,
                            updated_by = %s,
                            updated_at = NOW()
                        WHERE policy_id = %s
                        RETURNING *;
                    """
                    cur.execute(
                        update_sql,
                        (
                            policy.ttl_expression,
                            policy.ttl_seconds,
                            policy.granularity,
                            policy.timestamp_column,
                            policy.grace_period_expression,
                            policy.grace_period_seconds,
                            policy.updated_by,
                            existing["policy_id"],
                        ),
                    )
                else:
                    insert_sql = """
                        INSERT INTO ttl_policies (
                            project_id, target_scope, tier, dataset_id, query_artifact_type,
                            ttl_expression, ttl_seconds, granularity, timestamp_column,
                            grace_period_expression, grace_period_seconds, updated_by
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING *;
                    """
                    cur.execute(
                        insert_sql,
                        (
                            policy.project_id,
                            policy.target_scope,
                            policy.tier,
                            policy.dataset_id,
                            policy.query_artifact_type,
                            policy.ttl_expression,
                            policy.ttl_seconds,
                            policy.granularity,
                            policy.timestamp_column,
                            policy.grace_period_expression,
                            policy.grace_period_seconds,
                            policy.updated_by,
                        ),
                    )
                row = dict(cur.fetchone())
                row["policy_id"] = str(row["policy_id"])
                conn.commit()
                return TTLPolicyContract(**row)
        finally:
            conn.close()

    def get_policy(
        self,
        project_id: Optional[str],
        target_scope: str,
        tier: Optional[str] = None,
        dataset_id: Optional[str] = None,
        query_artifact_type: Optional[str] = None,
    ) -> Optional[TTLPolicyContract]:
        """Retrieves an exact matching policy."""
        sql = """
            SELECT * FROM ttl_policies
            WHERE COALESCE(project_id, '__GLOBAL__') = COALESCE(%s, '__GLOBAL__')
              AND target_scope = %s
              AND COALESCE(tier, '') = COALESCE(%s, '')
              AND COALESCE(dataset_id, '') = COALESCE(%s, '')
              AND COALESCE(query_artifact_type, '') = COALESCE(%s, '');
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, (project_id, target_scope, tier, dataset_id, query_artifact_type))
                row = cur.fetchone()
                if not row:
                    return None
                d = dict(row)
                d["policy_id"] = str(d["policy_id"])
                return TTLPolicyContract(**d)
        finally:
            conn.close()

    def delete_dataset_policy(self, project_id: str, dataset_id: str, tier: str) -> bool:
        """Removes a dataset-explicit TTL override."""
        sql = """
            DELETE FROM ttl_policies
            WHERE project_id = %s AND target_scope = 'DATASET' AND dataset_id = %s AND tier = %s
            RETURNING policy_id;
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, (project_id, dataset_id, tier.upper()))
                row = cur.fetchone()
                conn.commit()
                return bool(row)
        finally:
            conn.close()

    def list_project_policies(self, project_id: str) -> List[TTLPolicyContract]:
        """Lists all policies defined for a project."""
        sql = "SELECT * FROM ttl_policies WHERE project_id = %s ORDER BY target_scope, tier, dataset_id;"
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, (project_id,))
                rows = cur.fetchall()
                result = []
                for r in rows:
                    d = dict(r)
                    d["policy_id"] = str(d["policy_id"])
                    result.append(TTLPolicyContract(**d))
                return result
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Dataset Partitions CRUD
    # ------------------------------------------------------------------
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
        """Registers an uploaded partition file (clearing older partition rows if overwrite=True)."""
        now = ingested_at or datetime.now(timezone.utc)
        tier_up = tier.upper()
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                if overwrite:
                    cur.execute(
                        "DELETE FROM dataset_partitions WHERE project_id = %s AND dataset_id = %s AND tier = %s;",
                        (project_id, dataset_id, tier_up),
                    )
                insert_sql = """
                    INSERT INTO dataset_partitions (
                        project_id, dataset_id, tier, object_key, storage_uri,
                        size_bytes, record_count, ingested_at, min_event_ts, max_event_ts, lifecycle_status
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'ACTIVE')
                    RETURNING *;
                """
                cur.execute(
                    insert_sql,
                    (
                        project_id,
                        dataset_id,
                        tier_up,
                        object_key,
                        storage_uri,
                        size_bytes,
                        record_count,
                        now,
                        min_event_ts,
                        max_event_ts,
                    ),
                )
                row = dict(cur.fetchone())
                row["partition_id"] = str(row["partition_id"])
                conn.commit()
                return DatasetPartitionContract(**row)
        finally:
            conn.close()

    def list_partitions(
        self,
        project_id: str,
        dataset_id: Optional[str] = None,
        tier: Optional[str] = None,
        lifecycle_status: Optional[str] = None,
    ) -> List[DatasetPartitionContract]:
        """Lists partition records for a project/dataset."""
        clauses = ["project_id = %s"]
        params: List[Any] = [project_id]
        if dataset_id:
            clauses.append("dataset_id = %s")
            params.append(dataset_id)
        if tier:
            clauses.append("tier = %s")
            params.append(tier.upper())
        if lifecycle_status:
            clauses.append("lifecycle_status = %s")
            params.append(lifecycle_status)

        sql = f"SELECT * FROM dataset_partitions WHERE {' AND '.join(clauses)} ORDER BY ingested_at ASC;"
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, tuple(params))
                rows = cur.fetchall()
                result = []
                for r in rows:
                    d = dict(r)
                    d["partition_id"] = str(d["partition_id"])
                    result.append(DatasetPartitionContract(**d))
                return result
        finally:
            conn.close()

    def update_partition_status(
        self,
        partition_id: str,
        lifecycle_status: str,
        soft_deleted_at: Optional[datetime] = None,
    ) -> None:
        sql = """
            UPDATE dataset_partitions
            SET lifecycle_status = %s,
                soft_deleted_at = %s
            WHERE partition_id = %s;
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, (lifecycle_status, soft_deleted_at, partition_id))
                conn.commit()
        finally:
            conn.close()

    def update_compacted_partition(
        self,
        partition_id: str,
        new_object_key: str,
        new_storage_uri: str,
        new_size_bytes: int,
        new_record_count: int,
        new_min_event_ts: Optional[datetime],
        new_max_event_ts: Optional[datetime],
    ) -> None:
        sql = """
            UPDATE dataset_partitions
            SET object_key = %s,
                storage_uri = %s,
                size_bytes = %s,
                record_count = %s,
                min_event_ts = %s,
                max_event_ts = %s
            WHERE partition_id = %s;
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    (
                        new_object_key,
                        new_storage_uri,
                        new_size_bytes,
                        new_record_count,
                        new_min_event_ts,
                        new_max_event_ts,
                        partition_id,
                    ),
                )
                conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Dataset Retention States CRUD
    # ------------------------------------------------------------------
    def upsert_dataset_state(self, state: DatasetRetentionStateContract) -> DatasetRetentionStateContract:
        sql = """
            INSERT INTO dataset_retention_states (
                project_id, dataset_id, tier, effective_policy_id, policy_source,
                effective_ttl_expression, effective_ttl_seconds, granularity, timestamp_column,
                grace_period_expression, grace_period_seconds, reference_timestamp,
                expires_at, soft_deleted_at, purge_after, purged_at,
                retention_hold, hold_reason, held_by, lifecycle_status, last_error, last_evaluated_at
            )
            VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s, %s, NOW()
            )
            ON CONFLICT (project_id, dataset_id, tier)
            DO UPDATE SET
                effective_policy_id = EXCLUDED.effective_policy_id,
                policy_source = EXCLUDED.policy_source,
                effective_ttl_expression = EXCLUDED.effective_ttl_expression,
                effective_ttl_seconds = EXCLUDED.effective_ttl_seconds,
                granularity = EXCLUDED.granularity,
                timestamp_column = EXCLUDED.timestamp_column,
                grace_period_expression = EXCLUDED.grace_period_expression,
                grace_period_seconds = EXCLUDED.grace_period_seconds,
                reference_timestamp = EXCLUDED.reference_timestamp,
                expires_at = EXCLUDED.expires_at,
                soft_deleted_at = EXCLUDED.soft_deleted_at,
                purge_after = EXCLUDED.purge_after,
                purged_at = EXCLUDED.purged_at,
                retention_hold = EXCLUDED.retention_hold,
                hold_reason = EXCLUDED.hold_reason,
                held_by = EXCLUDED.held_by,
                lifecycle_status = EXCLUDED.lifecycle_status,
                last_error = EXCLUDED.last_error,
                last_evaluated_at = NOW()
            RETURNING *;
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    (
                        state.project_id,
                        state.dataset_id,
                        state.tier.upper(),
                        state.effective_policy_id,
                        state.policy_source,
                        state.effective_ttl_expression,
                        state.effective_ttl_seconds,
                        state.granularity,
                        state.timestamp_column,
                        state.grace_period_expression,
                        state.grace_period_seconds,
                        state.reference_timestamp,
                        state.expires_at,
                        state.soft_deleted_at,
                        state.purge_after,
                        state.purged_at,
                        state.retention_hold,
                        state.hold_reason,
                        state.held_by,
                        state.lifecycle_status,
                        state.last_error,
                    ),
                )
                row = dict(cur.fetchone())
                if row.get("effective_policy_id"):
                    row["effective_policy_id"] = str(row["effective_policy_id"])
                conn.commit()
                res = DatasetRetentionStateContract(**row)
                res.auto_restored = state.auto_restored
                return res
        finally:
            conn.close()

    def get_dataset_state(
        self,
        project_id: str,
        dataset_id: str,
        tier: str = "BRONZE",
    ) -> Optional[DatasetRetentionStateContract]:
        sql = """
            SELECT * FROM dataset_retention_states
            WHERE project_id = %s AND dataset_id = %s AND tier = %s;
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, (project_id, dataset_id, tier.upper()))
                row = cur.fetchone()
                if not row:
                    return None
                d = dict(row)
                if d.get("effective_policy_id"):
                    d["effective_policy_id"] = str(d["effective_policy_id"])
                return DatasetRetentionStateContract(**d)
        finally:
            conn.close()

    def list_dataset_states(
        self,
        project_id: Optional[str] = None,
    ) -> List[DatasetRetentionStateContract]:
        if project_id:
            sql = "SELECT * FROM dataset_retention_states WHERE project_id = %s ORDER BY tier, dataset_id;"
            params: Tuple[Any, ...] = (project_id,)
        else:
            sql = "SELECT * FROM dataset_retention_states ORDER BY project_id, tier, dataset_id;"
            params = ()
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
                result = []
                for r in rows:
                    d = dict(r)
                    if d.get("effective_policy_id"):
                        d["effective_policy_id"] = str(d["effective_policy_id"])
                    result.append(DatasetRetentionStateContract(**d))
                return result
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Query Data Artifacts CRUD
    # ------------------------------------------------------------------
    def upsert_query_artifact(self, artifact: QueryDataArtifactContract) -> QueryDataArtifactContract:
        sql = """
            INSERT INTO query_data_artifacts (
                artifact_id, project_id, artifact_type, storage_uri, source_datasets,
                size_bytes, ttl_expression, ttl_seconds, created_at, expires_at,
                soft_deleted_at, purge_after, retention_hold, lifecycle_status
            )
            VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (artifact_id)
            DO UPDATE SET
                storage_uri = EXCLUDED.storage_uri,
                source_datasets = EXCLUDED.source_datasets,
                size_bytes = EXCLUDED.size_bytes,
                ttl_expression = EXCLUDED.ttl_expression,
                ttl_seconds = EXCLUDED.ttl_seconds,
                expires_at = EXCLUDED.expires_at,
                soft_deleted_at = EXCLUDED.soft_deleted_at,
                purge_after = EXCLUDED.purge_after,
                retention_hold = EXCLUDED.retention_hold,
                lifecycle_status = EXCLUDED.lifecycle_status
            RETURNING *;
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    (
                        artifact.artifact_id,
                        artifact.project_id,
                        artifact.artifact_type,
                        artifact.storage_uri,
                        json.dumps(artifact.source_datasets),
                        artifact.size_bytes,
                        artifact.ttl_expression,
                        artifact.ttl_seconds,
                        artifact.created_at,
                        artifact.expires_at,
                        artifact.soft_deleted_at,
                        artifact.purge_after,
                        artifact.retention_hold,
                        artifact.lifecycle_status,
                    ),
                )
                row = dict(cur.fetchone())
                conn.commit()
                return QueryDataArtifactContract(**row)
        finally:
            conn.close()

    def get_query_artifact(self, artifact_id: str) -> Optional[QueryDataArtifactContract]:
        sql = "SELECT * FROM query_data_artifacts WHERE artifact_id = %s;"
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, (artifact_id,))
                row = cur.fetchone()
                return QueryDataArtifactContract(**dict(row)) if row else None
        finally:
            conn.close()

    def list_query_artifacts(
        self,
        project_id: Optional[str] = None,
        artifact_type: Optional[str] = None,
        lifecycle_status: Optional[str] = None,
    ) -> List[QueryDataArtifactContract]:
        clauses = []
        params: List[Any] = []
        if project_id is not None:
            clauses.append("project_id = %s")
            params.append(project_id)
        if artifact_type is not None:
            clauses.append("artifact_type = %s")
            params.append(artifact_type)
        if lifecycle_status is not None:
            clauses.append("lifecycle_status = %s")
            params.append(lifecycle_status)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT * FROM query_data_artifacts {where} ORDER BY created_at DESC;"
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, tuple(params))
                rows = cur.fetchall()
                return [QueryDataArtifactContract(**dict(r)) for r in rows]
        finally:
            conn.close()

    def update_query_artifact_status(
        self,
        artifact_id: str,
        lifecycle_status: str,
        soft_deleted_at: Optional[datetime] = None,
        purge_after: Optional[datetime] = None,
    ) -> None:
        sql = """
            UPDATE query_data_artifacts
            SET lifecycle_status = %s,
                soft_deleted_at = %s,
                purge_after = %s
            WHERE artifact_id = %s;
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, (lifecycle_status, soft_deleted_at, purge_after, artifact_id))
                conn.commit()
        finally:
            conn.close()

    def purge_expired_query_history_logs(
        self,
        cutoff_utc: datetime,
        dry_run: bool = False,
    ) -> Tuple[int, int]:
        """
        Evaluates or purges rows in the `ai_queries` query execution history table older than `cutoff_utc` (FR-003).
        Returns (rows_count, estimated_bytes_reclaimed).
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                if dry_run:
                    cur.execute(
                        """
                        SELECT COUNT(*) AS cnt,
                               COALESCE(SUM(OCTET_LENGTH(prompt) + OCTET_LENGTH(response)), 0) AS total_bytes
                        FROM ai_queries
                        WHERE created_at <= %s;
                        """,
                        (cutoff_utc,),
                    )
                    row = cur.fetchone()
                    return (int(row["cnt"] or 0), int(row["total_bytes"] or 0)) if row else (0, 0)
                else:
                    cur.execute(
                        """
                        DELETE FROM ai_queries
                        WHERE created_at <= %s
                        RETURNING OCTET_LENGTH(prompt) + OCTET_LENGTH(response) AS row_bytes;
                        """,
                        (cutoff_utc,),
                    )
                    rows = cur.fetchall()
                    conn.commit()
                    total_bytes = sum(int(r.get("row_bytes") or 0) for r in rows)
                    return len(rows), total_bytes
        except Exception as e:
            logger.debug(f"Query history log purge notice: {e}")
            return 0, 0
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Active Operation Leases (T009)
    # ------------------------------------------------------------------
    def acquire_lease(
        self,
        project_id: str,
        dataset_id: str,
        operation_type: str,
        holder_id: Optional[str] = None,
        ttl_seconds: int = 300,
    ) -> str:
        """Acquires a time-bounded active operation lease on a dataset."""
        holder = holder_id or f"op-{uuid.uuid4().hex[:10]}"
        now = datetime.now(timezone.utc)
        expires = now + timedelta(seconds=ttl_seconds)
        sql = """
            INSERT INTO dataset_active_leases (project_id, dataset_id, operation_type, holder_id, acquired_at, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING lease_id;
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, (project_id, dataset_id, operation_type, holder, now, expires))
                row = cur.fetchone()
                conn.commit()
                return str(row["lease_id"])
        finally:
            conn.close()

    def release_lease(self, lease_id: str) -> None:
        """Releases an active operation lease by lease_id."""
        if not lease_id:
            return
        sql = "DELETE FROM dataset_active_leases WHERE lease_id = %s;"
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, (lease_id,))
                conn.commit()
        finally:
            conn.close()

    def has_active_lease(self, project_id: str, dataset_id: str, now: Optional[datetime] = None) -> bool:
        """Checks if any unexpired lease exists for the given project dataset (or wildcard '*')."""
        ref_now = now or datetime.now(timezone.utc)
        sql = """
            SELECT COUNT(*) as cnt FROM dataset_active_leases
            WHERE project_id = %s
              AND (dataset_id = %s OR dataset_id = '*')
              AND expires_at > %s;
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, (project_id, dataset_id, ref_now))
                row = cur.fetchone()
                return int(row["cnt"]) > 0 if row else False
        finally:
            conn.close()

    def cleanup_expired_leases(self, now: Optional[datetime] = None) -> int:
        """Purges expired lease rows."""
        ref_now = now or datetime.now(timezone.utc)
        sql = "DELETE FROM dataset_active_leases WHERE expires_at <= %s;"
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, (ref_now,))
                deleted = cur.rowcount
                conn.commit()
                return deleted
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Cleanup Job Runs & Lineage Tombstones CRUD
    # ------------------------------------------------------------------
    def record_cleanup_run(self, run: CleanupJobRunContract) -> CleanupJobRunContract:
        sql = """
            INSERT INTO cleanup_job_runs (
                run_id, trigger_type, project_id, initiated_by, status,
                datasets_evaluated, datasets_soft_deleted, datasets_purged,
                partitions_compacted, rows_pruned, query_artifacts_purged,
                graph_elements_pruned, tombstones_created, bytes_reclaimed,
                skipped_held_count, skipped_locked_count, candidate_items, errors,
                started_at, completed_at, duration_ms
            )
            VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s::jsonb, %s::jsonb,
                %s, %s, %s
            )
            ON CONFLICT (run_id)
            DO UPDATE SET
                status = EXCLUDED.status,
                datasets_evaluated = EXCLUDED.datasets_evaluated,
                datasets_soft_deleted = EXCLUDED.datasets_soft_deleted,
                datasets_purged = EXCLUDED.datasets_purged,
                partitions_compacted = EXCLUDED.partitions_compacted,
                rows_pruned = EXCLUDED.rows_pruned,
                query_artifacts_purged = EXCLUDED.query_artifacts_purged,
                graph_elements_pruned = EXCLUDED.graph_elements_pruned,
                tombstones_created = EXCLUDED.tombstones_created,
                bytes_reclaimed = EXCLUDED.bytes_reclaimed,
                skipped_held_count = EXCLUDED.skipped_held_count,
                skipped_locked_count = EXCLUDED.skipped_locked_count,
                candidate_items = EXCLUDED.candidate_items,
                errors = EXCLUDED.errors,
                completed_at = EXCLUDED.completed_at,
                duration_ms = EXCLUDED.duration_ms
            RETURNING *;
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    (
                        run.run_id,
                        run.trigger_type,
                        run.project_id,
                        run.initiated_by,
                        run.status,
                        run.datasets_evaluated,
                        run.datasets_soft_deleted,
                        run.datasets_purged,
                        run.partitions_compacted,
                        run.rows_pruned,
                        run.query_artifacts_purged,
                        run.graph_elements_pruned,
                        run.tombstones_created,
                        run.bytes_reclaimed,
                        run.skipped_held_count,
                        run.skipped_locked_count,
                        json.dumps(run.candidate_items),
                        json.dumps(run.errors),
                        run.started_at,
                        run.completed_at,
                        run.duration_ms,
                    ),
                )
                row = dict(cur.fetchone())
                row["run_id"] = str(row["run_id"])
                conn.commit()
                return CleanupJobRunContract(**row)
        finally:
            conn.close()

    def list_cleanup_runs(
        self,
        project_id: Optional[str] = None,
        limit: int = 20,
    ) -> List[CleanupJobRunContract]:
        if project_id:
            sql = "SELECT * FROM cleanup_job_runs WHERE project_id = %s ORDER BY started_at DESC LIMIT %s;"
            params: Tuple[Any, ...] = (project_id, limit)
        else:
            sql = "SELECT * FROM cleanup_job_runs ORDER BY started_at DESC LIMIT %s;"
            params = (limit,)
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
                result = []
                for r in rows:
                    d = dict(r)
                    d["run_id"] = str(d["run_id"])
                    result.append(CleanupJobRunContract(**d))
                return result
        finally:
            conn.close()

    def record_tombstone(self, tombstone: LineageTombstoneContract) -> LineageTombstoneContract:
        sql = """
            INSERT INTO lineage_tombstones (
                project_id, dataset_id, tier, applied_ttl_expression,
                purged_at, upstream_datasets, downstream_datasets, cleanup_run_id
            )
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s)
            ON CONFLICT (project_id, dataset_id, tier)
            DO UPDATE SET
                applied_ttl_expression = EXCLUDED.applied_ttl_expression,
                purged_at = EXCLUDED.purged_at,
                upstream_datasets = EXCLUDED.upstream_datasets,
                downstream_datasets = EXCLUDED.downstream_datasets,
                cleanup_run_id = EXCLUDED.cleanup_run_id
            RETURNING *;
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    (
                        tombstone.project_id,
                        tombstone.dataset_id,
                        tombstone.tier.upper(),
                        tombstone.applied_ttl_expression,
                        tombstone.purged_at,
                        json.dumps(tombstone.upstream_datasets),
                        json.dumps(tombstone.downstream_datasets),
                        tombstone.cleanup_run_id,
                    ),
                )
                row = dict(cur.fetchone())
                if row.get("cleanup_run_id"):
                    row["cleanup_run_id"] = str(row["cleanup_run_id"])
                conn.commit()
                return LineageTombstoneContract(**row)
        finally:
            conn.close()

    def list_tombstones(self, project_id: str) -> List[LineageTombstoneContract]:
        sql = "SELECT * FROM lineage_tombstones WHERE project_id = %s ORDER BY purged_at DESC;"
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, (project_id,))
                rows = cur.fetchall()
                result = []
                for r in rows:
                    d = dict(r)
                    if d.get("cleanup_run_id"):
                        d["cleanup_run_id"] = str(d["cleanup_run_id"])
                    result.append(LineageTombstoneContract(**d))
                return result
        finally:
            conn.close()
