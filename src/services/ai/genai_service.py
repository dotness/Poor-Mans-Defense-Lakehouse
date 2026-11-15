import logging
import re
import time
from typing import Any, Dict, List, Optional

from google import genai
from src.config.settings import settings
from src.core.exceptions import ConfigurationError, ServiceUnavailableError
from src.services.graph.memgraph_client import MemgraphClient
from src.services.ai.cache import QueryCache
from src.services.ai.audit_logger import AuditLogger

logger = logging.getLogger(__name__)

STOP_WORDS = {
    "what", "are", "the", "is", "in", "of", "to", "for", "a", "an", "and", "or",
    "with", "by", "on", "at", "from", "which", "who", "whom", "this", "that",
    "these", "those", "how", "why", "when", "where", "show", "tell", "me", "find",
    "associated", "related", "any", "all", "recent", "about",
}


class GenAIService:
    """Service to handle RAG intelligence queries using Google AI Studio and Memgraph."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        memgraph_client: Optional[MemgraphClient] = None,
        cache: Optional[QueryCache] = None,
        audit_logger: Optional[AuditLogger] = None,
        client: Optional[genai.Client] = None,
    ):
        self.api_key = settings.google_api_key if api_key is None else api_key
        self.model = model or settings.gemini_model
        self.memgraph_client = memgraph_client or MemgraphClient()
        self.cache = cache or QueryCache()
        self.audit_logger = audit_logger or AuditLogger()

        if client is not None:
            self._client = client
        else:
            is_placeholder_key = not self.api_key or "your_google_ai_studio_api_key_here" in self.api_key
            if is_placeholder_key:
                raise ConfigurationError(
                    "Google AI Studio API key is missing or set to placeholder value.",
                    key="google_api_key",
                )
            try:
                self._client = genai.Client(api_key=self.api_key)
            except Exception as e:
                raise ConfigurationError(
                    f"Could not initialize Google GenAI client: {e}",
                    key="google_api_key",
                ) from e

    def _extract_search_terms(self, prompt: str) -> List[str]:
        words = re.findall(r"\b[A-Za-z0-9_\-\.]{2,}\b", prompt)
        raw_terms = [w.lower() for w in words if w.lower() not in STOP_WORDS]
        terms = set(raw_terms)
        for w in raw_terms:
            if w.endswith("ies") and len(w) > 3:
                terms.add(w[:-3] + "y")
            elif w.endswith("es") and len(w) > 3:
                terms.add(w[:-2])
            elif w.endswith("s") and len(w) > 2:
                terms.add(w[:-1])
        return list(terms) or [prompt.strip()]

    def retrieve_context(self, prompt: str) -> List[Dict[str, Any]]:
        terms = self._extract_search_terms(prompt)
        combined_context: List[Dict[str, Any]] = []
        seen = set()

        for term in terms:
            results = self.memgraph_client.find_related_entities(term, limit=10)
            for r in results:
                key = str(r)
                if key not in seen:
                    seen.add(key)
                    combined_context.append(r)

        return combined_context

    def _format_context(self, context: List[Dict[str, Any]]) -> str:
        if not context:
            return "No matching entities found in Memgraph intelligence graph."

        lines = []
        for c in context:
            if "relation" in c and c["relation"]:
                lines.append(
                    f"- Entity '{c.get('entity')}' ({c.get('type')}) -[{c.get('relation')}]-> '{c.get('connected_entity')}'"
                )
            elif "node" in c:
                node = c["node"]
                lines.append(f"- Entity '{node.get('name')}' ({node.get('label')})")
            else:
                lines.append(f"- {c}")

        return "\n".join(lines)

    def ask(self, prompt: str, user_id: str = "analyst") -> Dict[str, Any]:
        """Executes a natural language question with graph augmentation and semantic caching."""
        start_time = time.time()

        # 1. Rate Limit Check
        if not self.cache.check_rate_limit(user_id, limit=60, window_seconds=60):
            raise PermissionError(f"Rate limit exceeded for user '{user_id}'.")

        # 2. Check Semantic Cache
        cached_response = self.cache.get(prompt)
        if cached_response is not None:
            duration_ms = int((time.time() - start_time) * 1000)
            query_id = self.audit_logger.log_query(
                user_id=user_id,
                prompt=prompt,
                response=cached_response,
                model_used=self.model,
                duration_ms=duration_ms,
                cached=True,
                context_payload={"source": "cache"},
            )
            return {
                "response": cached_response,
                "cached": True,
                "model_used": self.model,
                "duration_ms": duration_ms,
                "context": [],
                "query_id": query_id,
            }

        # 3. Retrieve Graph Context
        context = self.retrieve_context(prompt)
        formatted_context = self._format_context(context)

        # 4. Generate Response via Google AI Studio
        augmented_prompt = (
            "You are Artemis AI, an intelligence analyst assistant for sovereign data systems.\n"
            "Answer the user query grounded STRICTLY on the knowledge graph context below.\n\n"
            f"=== GRAPH CONTEXT ===\n{formatted_context}\n\n"
            f"=== ANALYST QUESTION ===\n{prompt}\n\n"
            "Provide a clear, structured analytical response."
        )
        try:
            ai_resp = self._client.models.generate_content(
                model=self.model,
                contents=augmented_prompt,
            )
            response_text = ai_resp.text or "No response received from Google AI Studio."
        except Exception as e:
            logger.error(f"Google AI Studio inference failed: {e}")
            raise ServiceUnavailableError(
                f"Google AI Studio inference failed: {e}",
                service="gemini",
                original_cause=e,
            ) from e

        duration_ms = int((time.time() - start_time) * 1000)

        # 5. Store in Semantic Cache
        self.cache.set(prompt, response_text, ttl=3600)

        # 6. Audit Log
        query_id = self.audit_logger.log_query(
            user_id=user_id,
            prompt=prompt,
            response=response_text,
            model_used=self.model,
            duration_ms=duration_ms,
            cached=False,
            context_payload={"context_items": context},
        )

        return {
            "response": response_text,
            "cached": False,
            "model_used": self.model,
            "duration_ms": duration_ms,
            "context": context,
            "query_id": query_id,
        }
