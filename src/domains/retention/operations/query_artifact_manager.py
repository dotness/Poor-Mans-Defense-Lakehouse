import json
import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from src.domains.retention.models.contract.retention import QueryDataArtifactContract
from src.domains.retention.operations.retention_repository import RetentionRepository
from src.domains.retention.operations.policy_resolver import PolicyResolver

logger = logging.getLogger("artemis.retention.query_artifact_manager")


class QueryArtifactManager:
    """
    Governs TTL lifecycle for query data artifacts (FR-003, FR-004):
    - SQL_RESULT_CACHE (ephemeral Redis cache, invalidated when source dataset expires)
    - AI_RAG_CACHE (ephemeral Redis cache, invalidated when source dataset expires)
    - MATERIALIZED_EXPORT (saved query export in MinIO, governed independently by its own TTL)
    - QUERY_HISTORY_LOG (query execution audit records, governed independently by their own TTL)
    """

    def __init__(
        self,
        repository: Optional[RetentionRepository] = None,
        policy_resolver: Optional[PolicyResolver] = None,
        query_cache: Optional[Any] = None,
        s3_storage: Optional[Any] = None,
    ):
        self.repo = repository or RetentionRepository()
        self.resolver = policy_resolver or PolicyResolver(repository=self.repo)
        self._query_cache = query_cache
        self._s3_storage = s3_storage

    @property
    def query_cache(self):
        if self._query_cache is None:
            try:
                from src.services.ai.cache import QueryCache
                self._query_cache = QueryCache()
            except Exception:
                self._query_cache = None
        return self._query_cache

    @property
    def s3_storage(self):
        if self._s3_storage is None:
            try:
                from src.domains.project.operations.s3_storage import ProjectS3Storage
                self._s3_storage = ProjectS3Storage()
            except Exception:
                self._s3_storage = None
        return self._s3_storage

    def register_sql_cache_entry(
        self,
        project_id: Optional[str],
        sql: str,
        result_payload: Dict[str, Any],
        source_datasets: Optional[List[Dict[str, str]]] = None,
        explicit_ttl_expression: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> QueryDataArtifactContract:
        """Caches an analytical SQL query response with a governed TTL and tracks dataset dependencies."""
        ref_now = now or datetime.now(timezone.utc)
        policy = self.resolver.resolve_query_artifact_policy(
            project_id=project_id,
            artifact_type="SQL_RESULT_CACHE",
            explicit_ttl_expression=explicit_ttl_expression,
        )
        ttl_sec = policy.ttl_seconds or 3600
        payload_json = json.dumps(result_payload, default=str)
        cache_key = f"artemis:sql:cache:{uuid.uuid4().hex[:12]}"
        if self.query_cache is not None:
            cache_key = self.query_cache.set_sql(
                project_id=project_id,
                sql=sql,
                payload_json=payload_json,
                ttl=ttl_sec,
                source_datasets=source_datasets,
            )

        expires_at = ref_now + timedelta(seconds=ttl_sec) if policy.ttl_seconds is not None else None
        artifact = QueryDataArtifactContract(
            artifact_id=cache_key,
            project_id=project_id,
            artifact_type="SQL_RESULT_CACHE",
            storage_uri=f"redis://{cache_key}",
            source_datasets=source_datasets or [],
            size_bytes=len(payload_json.encode("utf-8")),
            ttl_expression=policy.ttl_expression,
            ttl_seconds=policy.ttl_seconds,
            created_at=ref_now,
            expires_at=expires_at,
            lifecycle_status="ACTIVE",
        )
        return self.repo.upsert_query_artifact(artifact)

    def register_ai_cache_entry(
        self,
        project_id: Optional[str],
        prompt: str,
        response_text: str,
        source_datasets: Optional[List[Dict[str, str]]] = None,
        explicit_ttl_expression: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> QueryDataArtifactContract:
        """Caches an AI RAG response with a governed TTL and tracks dataset dependencies."""
        ref_now = now or datetime.now(timezone.utc)
        policy = self.resolver.resolve_query_artifact_policy(
            project_id=project_id,
            artifact_type="AI_RAG_CACHE",
            explicit_ttl_expression=explicit_ttl_expression,
        )
        ttl_sec = policy.ttl_seconds or 3600
        cache_key = f"artemis:ai:query:{uuid.uuid4().hex[:12]}"
        if self.query_cache is not None:
            cache_key = self.query_cache.set(
                prompt=prompt,
                response=response_text,
                ttl=ttl_sec,
                source_datasets=source_datasets,
            )

        expires_at = ref_now + timedelta(seconds=ttl_sec) if policy.ttl_seconds is not None else None
        artifact = QueryDataArtifactContract(
            artifact_id=cache_key,
            project_id=project_id,
            artifact_type="AI_RAG_CACHE",
            storage_uri=f"redis://{cache_key}",
            source_datasets=source_datasets or [],
            size_bytes=len(response_text.encode("utf-8")),
            ttl_expression=policy.ttl_expression,
            ttl_seconds=policy.ttl_seconds,
            created_at=ref_now,
            expires_at=expires_at,
            lifecycle_status="ACTIVE",
        )
        return self.repo.upsert_query_artifact(artifact)

    def materialize_query_export(
        self,
        project_id: str,
        export_dataset_id: str,
        columns: List[str],
        rows: List[List[Any]],
        source_datasets: Optional[List[Dict[str, str]]] = None,
        explicit_ttl_expression: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> QueryDataArtifactContract:
        """
        Materializes a query result set as a standalone governed query export artifact (FR-003, FR-004).
        Materialized exports follow their own assigned TTL independently once created.
        """
        ref_now = now or datetime.now(timezone.utc)
        policy = self.resolver.resolve_query_artifact_policy(
            project_id=project_id,
            artifact_type="MATERIALIZED_EXPORT",
            explicit_ttl_expression=explicit_ttl_expression,
        )

        # Serialize result rows to JSONL bytes and upload to S3 if available
        records = [dict(zip(columns, r)) for r in rows]
        jsonl_bytes = "\n".join(json.dumps(rec, default=str) for rec in records).encode("utf-8")
        size_bytes = len(jsonl_bytes)
        storage_uri = f"s3://telemetry/projects/{project_id}/query_exports/{export_dataset_id}.parquet"

        if self.s3_storage is not None:
            try:
                storage_uri, _, size_bytes = self.s3_storage.upload_tabular_data(
                    project_id=project_id,
                    dataset_name=export_dataset_id,
                    tier="query_exports",
                    data_bytes=jsonl_bytes if jsonl_bytes else b"{}\n",
                    filename=f"{export_dataset_id}.jsonl",
                )
            except Exception as e:
                logger.debug(f"Materialized query export fallback URI used ({e})")

        expires_at = (
            ref_now + timedelta(seconds=policy.ttl_seconds)
            if policy.ttl_seconds is not None
            else None
        )
        artifact = QueryDataArtifactContract(
            artifact_id=export_dataset_id,
            project_id=project_id,
            artifact_type="MATERIALIZED_EXPORT",
            storage_uri=storage_uri,
            source_datasets=source_datasets or [],
            size_bytes=size_bytes,
            ttl_expression=policy.ttl_expression,
            ttl_seconds=policy.ttl_seconds,
            created_at=ref_now,
            expires_at=expires_at,
            lifecycle_status="ACTIVE",
        )
        return self.repo.upsert_query_artifact(artifact)

    def invalidate_ephemeral_caches_for_dataset(
        self,
        project_id: str,
        dataset_id: str,
    ) -> int:
        """
        Immediately invalidates ephemeral SQL_RESULT_CACHE and AI_RAG_CACHE artifacts that depend
        on (project_id, dataset_id) when that source dataset expires or is soft-deleted (FR-003).
        Explicit MATERIALIZED_EXPORT and QUERY_HISTORY_LOG artifacts are untouched and follow their own TTL.
        """
        invalidated_count = 0
        if self.query_cache is not None:
            try:
                self.query_cache.invalidate_for_dataset(project_id, dataset_id)
            except Exception as e:
                logger.debug(f"Redis cache invalidation notice: {e}")

        active_artifacts = self.repo.list_query_artifacts(lifecycle_status="ACTIVE")
        for art in active_artifacts:
            if art.artifact_type not in ("SQL_RESULT_CACHE", "AI_RAG_CACHE"):
                continue
            depends = any(
                d.get("project_id") == project_id and d.get("dataset_id") == dataset_id
                for d in (art.source_datasets or [])
            )
            if depends or (art.project_id == project_id and not art.source_datasets):
                self.repo.update_query_artifact_status(
                    artifact_id=art.artifact_id,
                    lifecycle_status="PURGED",
                )
                invalidated_count += 1

        return invalidated_count
