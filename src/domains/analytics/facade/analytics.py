import logging
import time
from typing import Optional
from src.base.facade import DomainFacade
from src.domains.analytics.models.contract.query import QueryRequestContract, QueryResultContract
from src.services.analytics.query_service import QueryService

logger = logging.getLogger(__name__)


class AnalyticsFacade(DomainFacade):
    """Facade for embedded vectorized DuckDB SQL analytics."""

    def __init__(self, service: Optional[QueryService] = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.service = service or QueryService()

    async def execute_query(self, request: QueryRequestContract) -> QueryResultContract:
        """Executes a SQL query against MinIO Parquet and returns formatted contract, registering optional query TTL artifacts."""
        formatted_output, meta = self.service.execute(
            sql=request.sql,
            output_format=request.format,
        )
        columns = meta.get("columns", [])
        rows = meta.get("rows", [])
        row_count = meta.get("row_count", 0)
        duration_ms = int(meta.get("duration_seconds", 0) * 1000)
        export_artifact_id = None

        if request.cache_ttl or request.export_dataset:
            try:
                from src.domains.retention.operations.query_artifact_manager import QueryArtifactManager
                art_mgr = QueryArtifactManager()
                if request.cache_ttl:
                    art_mgr.register_sql_cache_entry(
                        project_id=None,
                        sql=request.sql,
                        result_payload={"columns": columns, "row_count": row_count, "formatted_output": formatted_output},
                        explicit_ttl_expression=request.cache_ttl,
                    )
                if request.export_dataset:
                    exp_art = art_mgr.materialize_query_export(
                        project_id="global",
                        export_dataset_id=request.export_dataset,
                        columns=columns,
                        rows=rows,
                        explicit_ttl_expression=request.export_ttl,
                    )
                    export_artifact_id = exp_art.artifact_id
            except ValueError:
                raise
            except Exception as e:
                logger.debug(f"AnalyticsFacade query artifact registration notice: {e}")

        return QueryResultContract(
            columns=columns,
            rows=[],  # Formatted text has representation
            row_count=row_count,
            duration_ms=duration_ms,
            formatted_output=formatted_output,
            export_artifact_id=export_artifact_id,
        )
