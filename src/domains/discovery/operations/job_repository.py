import logging
import uuid
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import psycopg2
from psycopg2.extras import RealDictCursor

try:
    from src.config.settings import settings
    from src.domains.discovery.models.contract.discovery import IndexJobContract
except ImportError:
    from config.settings import settings
    from domains.discovery.models.contract.discovery import IndexJobContract

logger = logging.getLogger("artemis.discovery.job_repository")


class IndexJobRepository:
    """Repository for managing kdg_index_jobs persistence in PostgreSQL."""

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

    def _get_connection(self):
        return psycopg2.connect(
            host=self.host,
            port=self.port,
            dbname=self.dbname,
            user=self.user,
            password=self.password,
            cursor_factory=RealDictCursor,
        )

    def ensure_tables(self) -> None:
        """Ensures kdg_index_jobs table exists."""
        query = """
        CREATE TABLE IF NOT EXISTS kdg_index_jobs (
            job_id VARCHAR(64) PRIMARY KEY,
            project_id VARCHAR(64) NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
            resource_id VARCHAR(128) NOT NULL,
            phase VARCHAR(32) NOT NULL DEFAULT 'structural',
            status VARCHAR(32) NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 1,
            error TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_kdg_index_jobs_project ON kdg_index_jobs(project_id);
        CREATE INDEX IF NOT EXISTS idx_kdg_index_jobs_status ON kdg_index_jobs(status);
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query)
                conn.commit()
        except Exception as e:
            logger.warning(f"Could not ensure kdg_index_jobs table: {e}")

    def create_job(
        self,
        project_id: str,
        resource_id: str,
        phase: str = "structural",
    ) -> IndexJobContract:
        """Creates a new indexing job."""
        job_id = str(uuid.uuid4())
        query = """
            INSERT INTO kdg_index_jobs (job_id, project_id, resource_id, phase, status, attempts, error, created_at, updated_at)
            VALUES (%s, %s, %s, %s, 'pending', 1, NULL, NOW(), NOW())
            RETURNING job_id, project_id, resource_id, phase, status, attempts, error, created_at, updated_at;
        """
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (job_id, project_id, resource_id, phase))
                row = cur.fetchone()
                conn.commit()
                return IndexJobContract(**row)

    def update_status(
        self,
        job_id: str,
        status: str,
        error: Optional[str] = None,
    ) -> Optional[IndexJobContract]:
        """Transitions job status (e.g. running, completed, failed, skipped_no_ai)."""
        query = """
            UPDATE kdg_index_jobs
            SET status = %s, error = %s, updated_at = NOW()
            WHERE job_id = %s
            RETURNING job_id, project_id, resource_id, phase, status, attempts, error, created_at, updated_at;
        """
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (status, error, job_id))
                row = cur.fetchone()
                conn.commit()
                return IndexJobContract(**row) if row else None

    def transition_status(
        self,
        job_id: str,
        status: str,
        phase: Optional[str] = None,
        error: Optional[str] = None,
    ) -> Optional[IndexJobContract]:
        """Transitions job status and optionally phase."""
        if phase:
            query = """
                UPDATE kdg_index_jobs
                SET status = %s, phase = %s, error = %s, updated_at = NOW()
                WHERE job_id = %s
                RETURNING job_id, project_id, resource_id, phase, status, attempts, error, created_at, updated_at;
            """
            params = (status, phase, error, job_id)
        else:
            query = """
                UPDATE kdg_index_jobs
                SET status = %s, error = %s, updated_at = NOW()
                WHERE job_id = %s
                RETURNING job_id, project_id, resource_id, phase, status, attempts, error, created_at, updated_at;
            """
            params = (status, error, job_id)

        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                row = cur.fetchone()
                conn.commit()
                return IndexJobContract(**row) if row else None

    def record_failure(self, job_id: str, error_message: str) -> Optional[IndexJobContract]:
        """Records a job failure with an error message."""
        return self.transition_status(job_id, status="failed", error=error_message)

    def increment_attempt(self, job_id: str, max_attempts: int = 3) -> Optional[IndexJobContract]:
        """Increments attempt counter and sets status to pending if attempts <= max_attempts, else failed."""
        query = """
            UPDATE kdg_index_jobs
            SET attempts = attempts + 1,
                status = CASE WHEN attempts + 1 <= %s THEN 'pending' ELSE 'failed' END,
                updated_at = NOW()
            WHERE job_id = %s
            RETURNING job_id, project_id, resource_id, phase, status, attempts, error, created_at, updated_at;
        """
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (max_attempts, job_id))
                row = cur.fetchone()
                conn.commit()
                return IndexJobContract(**row) if row else None

    def get_job(self, job_id: str) -> Optional[IndexJobContract]:
        """Fetches a specific job by job_id."""
        query = """
            SELECT job_id, project_id, resource_id, phase, status, attempts, error, created_at, updated_at
            FROM kdg_index_jobs
            WHERE job_id = %s;
        """
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (job_id,))
                row = cur.fetchone()
                return IndexJobContract(**row) if row else None

    def list_jobs(
        self,
        project_id: str,
        status: Optional[str] = None,
    ) -> List[IndexJobContract]:
        """Lists jobs for a project, optionally filtered by status."""
        if status:
            query = """
                SELECT job_id, project_id, resource_id, phase, status, attempts, error, created_at, updated_at
                FROM kdg_index_jobs
                WHERE project_id = %s AND status = %s
                ORDER BY created_at DESC;
            """
            params = (project_id, status)
        else:
            query = """
                SELECT job_id, project_id, resource_id, phase, status, attempts, error, created_at, updated_at
                FROM kdg_index_jobs
                WHERE project_id = %s
                ORDER BY created_at DESC;
            """
            params = (project_id,)

        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                rows = cur.fetchall()
                return [IndexJobContract(**r) for r in rows]
