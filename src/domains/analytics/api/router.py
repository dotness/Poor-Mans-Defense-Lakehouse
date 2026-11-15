from fastapi import APIRouter
from src.domains.analytics.facade.analytics import AnalyticsFacade
from src.domains.analytics.models.contract.query import QueryRequestContract, QueryResultContract

router = APIRouter(prefix="/api/v1/analytics", tags=["Analytics"])


@router.post("/query", response_model=QueryResultContract)
async def query(query_req: QueryRequestContract):
    """Executes a vectorized analytical SQL query against MinIO Parquet."""
    facade = AnalyticsFacade()
    result = await facade.execute_query(query_req)
    return result
