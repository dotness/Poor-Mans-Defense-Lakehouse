import uuid
from typing import Any, Dict, List, Optional


class MockAuditLogger:
    """In-memory test double for AuditLogger."""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        dbname: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self.host = host
        self.port = port
        self.dbname = dbname
        self.user = user
        self.password = password
        self.logs: List[Dict[str, Any]] = []

    def log_query(
        self,
        user_id: str,
        prompt: str,
        response: str,
        model_used: str,
        duration_ms: int,
        cached: bool = False,
        context_payload: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Records an AI query to in-memory log list and returns generated query_id."""
        query_id = str(uuid.uuid4())
        record = {
            "query_id": query_id,
            "user_id": user_id,
            "prompt": prompt,
            "context_payload": context_payload or {},
            "response": response,
            "model_used": model_used,
            "cached": cached,
            "duration_ms": duration_ms,
        }
        self.logs.append(record)
        return query_id

    def get_logs(self) -> List[Dict[str, Any]]:
        return list(self.logs)

    def get_recent_logs(self, limit: int = 10) -> List[Dict[str, Any]]:
        return list(reversed(self.logs))[:limit]

    def clear(self) -> None:
        self.logs.clear()
