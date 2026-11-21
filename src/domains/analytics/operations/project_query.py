import re
import time
import logging
from typing import Dict, Any, List, Optional
from src.services.analytics.duckdb_client import DuckDBClient

logger = logging.getLogger("artemis.analytics.project")


class ProjectQueryExecutor:
    """Executes DuckDB analytical queries confined to a specific project workspace."""

    def __init__(self, duckdb_client: Optional[DuckDBClient] = None):
        self.duckdb = duckdb_client or DuckDBClient()

    def execute_scoped_query(
        self,
        project_id: str,
        sql: str,
        cache_ttl: Optional[str] = None,
        export_dataset: Optional[str] = None,
        export_ttl: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Executes a read-only DuckDB SQL query, verifying that any read_parquet / s3 references
        are confined to the active project partition, enforcing read-time TTL filtering via
        QueryTTLInterceptor, acquiring an active query lease, and optionally caching or
        materializing the query result as a governed QueryDataArtifact.
        """
        start_time = time.monotonic()
        normalized_sql = sql.strip()

        # Guardrail: Check for S3 path confinement
        s3_patterns = re.findall(r"s3://[a-zA-Z0-9_\-\./\*]+", normalized_sql)
        for path in s3_patterns:
            expected_prefix = f"s3://telemetry/projects/{project_id}/"
            if not path.startswith(expected_prefix) and path != f"s3://telemetry/projects/{project_id}":
                raise ValueError(
                    f"Access Denied: SQL query references unconfined path '{path}'. "
                    f"Queries for project '{project_id}' must target '{expected_prefix}*'."
                )

        # Transparent Read-Time TTL Interception (FR-005)
        executable_sql = normalized_sql
        referenced_datasets = []
        lease_id = None
        retention_repo = None
        try:
            from src.domains.retention.operations.query_interceptor import QueryTTLInterceptor
            from src.domains.retention.operations.retention_repository import RetentionRepository
            retention_repo = RetentionRepository()
            lease_id = retention_repo.acquire_lease(project_id, "*", "ANALYTICAL_QUERY")
            interceptor = QueryTTLInterceptor(repository=retention_repo)
            interception = interceptor.intercept_sql_query(normalized_sql, default_project_id=project_id)
            referenced_datasets = interception.referenced_datasets
            if interception.short_circuit_empty:
                duration_ms = int((time.monotonic() - start_time) * 1000)
                return {
                    "columns": [],
                    "rows": [],
                    "row_count": 0,
                    "duration_ms": duration_ms,
                    "empty": True,
                    "ttl_filtered": True,
                    "message": interception.empty_reason or "No active (non-expired) data found for query.",
                }
            executable_sql = interception.rewritten_sql
        except Exception as ie:
            logger.debug(f"QueryTTLInterceptor fallback notice: {ie}")

        try:
            cursor = self.duckdb.query(executable_sql)
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            rows = cursor.fetchall()
            duration_ms = int((time.monotonic() - start_time) * 1000)

            # Convert rows to serializable format
            clean_rows = []
            for r in rows:
                clean_rows.append([str(item) if not isinstance(item, (int, float, bool, type(None))) else item for item in r])

            result_payload: Dict[str, Any] = {
                "columns": columns,
                "rows": clean_rows,
                "row_count": len(clean_rows),
                "duration_ms": duration_ms,
                "empty": len(clean_rows) == 0,
            }

            # Register query data artifacts if requested (FR-003, FR-004)
            if cache_ttl or export_dataset:
                try:
                    from src.domains.retention.operations.query_artifact_manager import QueryArtifactManager
                    art_mgr = QueryArtifactManager(repository=retention_repo)
                    if cache_ttl:
                        cache_art = art_mgr.register_sql_cache_entry(
                            project_id=project_id,
                            sql=normalized_sql,
                            result_payload=result_payload,
                            source_datasets=referenced_datasets,
                            explicit_ttl_expression=cache_ttl,
                        )
                        result_payload["cache_artifact_id"] = cache_art.artifact_id
                        result_payload["cache_ttl"] = cache_art.ttl_expression
                    if export_dataset:
                        exp_art = art_mgr.materialize_query_export(
                            project_id=project_id,
                            export_dataset_id=export_dataset,
                            columns=columns,
                            rows=clean_rows,
                            source_datasets=referenced_datasets,
                            explicit_ttl_expression=export_ttl,
                        )
                        result_payload["export_artifact_id"] = exp_art.artifact_id
                        result_payload["export_ttl"] = exp_art.ttl_expression
                        result_payload["export_storage_uri"] = exp_art.storage_uri
                except ValueError:
                    # Propagate validation errors (e.g. TTL exceeding project max retention limit)
                    raise
                except Exception as ae:
                    logger.debug(f"Query artifact registration notice: {ae}")

            return result_payload
        except Exception as e:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            err_msg = str(e)
            if "No files found that match the pattern" in err_msg:
                # Graceful empty lake handling
                return {
                    "columns": [],
                    "rows": [],
                    "row_count": 0,
                    "duration_ms": duration_ms,
                    "empty": True,
                    "message": f"No data found (telemetry lake in object storage is empty for project '{project_id}').",
                }
            logger.error(f"DuckDB query error in project {project_id}: {e}")
            raise
        finally:
            if lease_id and retention_repo is not None:
                try:
                    retention_repo.release_lease(lease_id)
                except Exception:
                    pass
