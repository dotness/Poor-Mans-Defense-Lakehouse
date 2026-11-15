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
    ) -> Dict[str, Any]:
        """
        Executes a read-only DuckDB SQL query, verifying that any read_parquet / s3 references
        are confined to the active project partition.
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

        try:
            cursor = self.duckdb.query(normalized_sql)
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            rows = cursor.fetchall()
            duration_ms = int((time.monotonic() - start_time) * 1000)

            # Convert rows to serializable format
            clean_rows = []
            for r in rows:
                clean_rows.append([str(item) if not isinstance(item, (int, float, bool, type(None))) else item for item in r])

            return {
                "columns": columns,
                "rows": clean_rows,
                "row_count": len(clean_rows),
                "duration_ms": duration_ms,
                "empty": len(clean_rows) == 0,
            }
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
