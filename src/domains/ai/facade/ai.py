import logging
from typing import Optional
from src.base.facade import DomainFacade
from src.domains.ai.models.contract.ai import AIQueryRequestContract, AIQueryResponseContract
from src.domains.graph.facade.graph import GraphFacade
from src.services.ai.genai_service import GenAIService
from src.services.ai.cache import QueryCache
from src.services.ai.audit_logger import AuditLogger

logger = logging.getLogger(__name__)


class AIFacade(DomainFacade):
    """Facade for AI Graph RAG intelligence correlation using Google AI Studio."""

    def __init__(
        self,
        graph_facade: Optional[GraphFacade] = None,
        service: Optional[GenAIService] = None,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.graph_facade = graph_facade or GraphFacade()
        self.service = service or GenAIService(
            memgraph_client=self.graph_facade.client,
            cache=QueryCache(),
            audit_logger=AuditLogger(),
        )

    async def ask(self, request: AIQueryRequestContract) -> AIQueryResponseContract:
        """Executes a Graph RAG query through the Google ADK multi-agent pipeline."""
        from src.domains.ai.operations.ai_agents import MultiAgentPipelineOperation
        from src.domains.ai.operations.dynamic_loop import DynamicAgentLoop
        from src.domains.ai.operations.tools import AgentTools

        if isinstance(self.user, dict):
            user_id = self.user.get("sub", self.user.get("username", request.user_id))
            user_ctx = self.user
        elif self.user and hasattr(self.user, "id"):
            user_id = self.user.id
            roles = getattr(self.user, "roles", ["admin"] if user_id == "admin" else ["user"])
            user_ctx = {"sub": user_id, "roles": roles}
        else:
            user_id = request.user_id
            user_ctx = {"sub": user_id, "roles": ["admin", "analyst"] if user_id == "admin" else ["user"]}

        tools = AgentTools(graph_facade=self.graph_facade, user=user_ctx)
        client = getattr(self.service, "_client", None)
        dynamic_loop = DynamicAgentLoop(tools=tools, client=client)
        pipeline = MultiAgentPipelineOperation(genai_service=self.service, dynamic_loop=dynamic_loop)
        result = await pipeline.run(prompt=request.prompt, user_id=user_id)

        return AIQueryResponseContract(
            query_id=result["query_id"],
            response=result["response"],
            model_used=result["model_used"],
            cached=result["cached"],
            duration_ms=result["duration_ms"],
            context=result["context"],
            tool_calls=result.get("tool_calls", []),
            databases_consulted=result.get("databases_consulted", []),
        )
