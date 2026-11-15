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
        """Executes a SQL query against MinIO Parquet and returns formatted contract."""
        formatted_output, meta = self.service.execute(
            sql=request.sql,
            output_format=request.format,
        )

        return QueryResultContract(
            columns=meta.get("columns", []),
            rows=[],  # Formatted text has representation
            row_count=meta.get("row_count", 0),
            duration_ms=int(meta.get("duration_seconds", 0) * 1000),
            formatted_output=formatted_output,
        )
