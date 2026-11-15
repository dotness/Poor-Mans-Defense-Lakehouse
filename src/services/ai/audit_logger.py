import json
import logging
import uuid
from typing import Any, Dict, List, Optional
import psycopg2

from src.config.settings import settings
from src.core.exceptions import ConnectionError, ServiceUnavailableError

logger = logging.getLogger(__name__)


class AuditLogger:
    """Logs AI natural language queries and RAG context to PostgreSQL."""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        dbname: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self.host = host or settings.postgres_host
        self.port = port or settings.postgres_port
        self.dbname = dbname or settings.postgres_db
        self.user = user or settings.postgres_user
        self.password = password or settings.postgres_password

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
        """Records an AI query to PostgreSQL ai_queries table."""
        query_id = str(uuid.uuid4())
        try:
            conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                dbname=self.dbname,
                user=self.user,
                password=self.password,
                connect_timeout=2,
            )
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ai_queries (query_id, user_id, prompt, context_payload, response, model_used, cached, duration_ms)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        query_id,
                        user_id,
                        prompt,
                        json.dumps(context_payload or {}),
                        response,
                        model_used,
                        cached,
                        duration_ms,
                    ),
                )
            conn.commit()
            conn.close()
            return query_id
        except Exception as e:
            logger.error(f"Could not persist AI query in PostgreSQL: {e}")
            raise ConnectionError(
                f"Could not persist AI query in PostgreSQL: {e}",
                host=self.host,
                port=self.port,
                original_cause=e,
            ) from e

    def get_recent_logs(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Fetches recent AI query logs from PostgreSQL."""
        try:
            conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                dbname=self.dbname,
                user=self.user,
                password=self.password,
                connect_timeout=2,
            )
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT query_id, user_id, prompt, response, model_used, cached, duration_ms, created_at
                    FROM ai_queries
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
                rows = cur.fetchall()
                conn.close()
                return [
                    {
                        "query_id": str(r[0]),
                        "user_id": r[1],
                        "prompt": r[2],
                        "response": r[3],
                        "model_used": r[4],
                        "cached": r[5],
                        "duration_ms": r[6],
                        "created_at": str(r[7]),
                    }
                    for r in rows
                ]
        except Exception as e:
            logger.error(f"Failed to fetch logs from PostgreSQL: {e}")
            raise ConnectionError(
                f"Failed to fetch logs from PostgreSQL: {e}",
                host=self.host,
                port=self.port,
                original_cause=e,
            ) from e
