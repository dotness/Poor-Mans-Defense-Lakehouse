from fastapi import APIRouter
from src.domains.ai.facade.ai import AIFacade
from src.domains.ai.models.contract.ai import AIQueryRequestContract, AIQueryResponseContract

router = APIRouter(prefix="/api/v1/ai", tags=["Artificial Intelligence"])


@router.post("/ask", response_model=AIQueryResponseContract)
async def ask(ai_req: AIQueryRequestContract):
    """Executes an autonomous dynamic tool query across DuckDB and Memgraph using Google AI Studio."""
    facade = AIFacade()
    result = await facade.ask(ai_req)
    return result
