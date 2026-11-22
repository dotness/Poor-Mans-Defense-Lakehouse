import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
import psycopg2
from psycopg2.extras import RealDictCursor, Json

try:
    from src.config.settings import settings
    from src.domains.pipeline.models.contract.project_pipeline import (
        PipelineCreateContract,
        PipelineUpdateContract,
        PipelineResponseContract,
        PipelineRunResponseContract,
    )
    from src.domains.pipeline.operations.script_validator import validate_python_script
    from src.domains.pipeline.operations.resource_validator import validate_pipeline_default_resources
except ImportError:
    from config.settings import settings
    from domains.pipeline.models.contract.project_pipeline import (
        PipelineCreateContract,
        PipelineUpdateContract,
        PipelineResponseContract,
        PipelineRunResponseContract,
    )
    from domains.pipeline.operations.script_validator import validate_python_script
    from domains.pipeline.operations.resource_validator import validate_pipeline_default_resources

logger = logging.getLogger("artemis.pipeline.manager")


class PipelineManager:
    """Manages Pipeline entity metadata and historical run tracking in PostgreSQL."""

    def __init__(self):
        self.host = settings.postgres_host
        self.port = settings.postgres_port
        self.dbname = settings.postgres_db
        self.user = settings.postgres_user
        self.password = settings.postgres_password
        self._schema_checked = False

    def _get_connection(self):
        conn = psycopg2.connect(
            host=self.host,
            port=self.port,
            dbname=self.dbname,
            user=self.user,
            password=self.password,
            cursor_factory=RealDictCursor,
        )
        if not self._schema_checked:
            self._ensure_resource_columns(conn)
            self._schema_checked = True
        return conn

    def _ensure_resource_columns(self, conn) -> None:
        """Ensures default_cpu_limit and default_memory_limit columns exist on project_pipelines."""
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    ALTER TABLE project_pipelines
                        ADD COLUMN IF NOT EXISTS default_cpu_limit DOUBLE PRECISION,
                        ADD COLUMN IF NOT EXISTS default_memory_limit VARCHAR(32);
                    """
                )
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.debug(f"Schema check for project_pipelines resource columns skipped: {e}")

    @staticmethod
    def _hydrate_run_row(row: Dict[str, Any], duration_ms: int = 0) -> PipelineRunResponseContract:
        row_data = dict(row)
        row_data["run_id"] = str(row_data["run_id"])
        row_data["pipeline_id"] = str(row_data["pipeline_id"])
        row_data["duration_ms"] = duration_ms
        details = row_data.get("details")
        if not isinstance(details, dict):
            details = {}
        row_data["details"] = details
        row_data["effective_cpu_limit"] = details.get("effective_cpu_limit")
        row_data["effective_memory_limit"] = details.get("effective_memory_limit")
        row_data["requested_cpu_limit"] = details.get("requested_cpu_limit")
        row_data["requested_memory_limit"] = details.get("requested_memory_limit")
        row_data["resource_clamped"] = bool(details.get("resource_clamped", False))
        return PipelineRunResponseContract(**row_data)

    def create_pipeline(
        self,
        project_id: str,
        contract: PipelineCreateContract,
        created_by: str = "admin",
    ) -> PipelineResponseContract:
        """Validates script syntax and resource defaults, then registers a new pipeline under a project."""
        is_valid, err = validate_python_script(contract.script_content)
        if not is_valid:
            raise ValueError(f"Invalid script syntax: {err}")

        validated_cpu, validated_mem = validate_pipeline_default_resources(
            default_cpu_limit=contract.default_cpu_limit,
            default_memory_limit=contract.default_memory_limit,
        )

        query = """
            INSERT INTO project_pipelines (
                project_id, name, description, stage, script_content, docker_image,
                default_cpu_limit, default_memory_limit, version, created_by, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 1, %s, NOW(), NOW())
            RETURNING pipeline_id, project_id, name, description, stage, docker_image,
                      default_cpu_limit, default_memory_limit, version, created_by, created_at, updated_at;
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    query,
                    (
                        project_id,
                        contract.name,
                        contract.description,
                        contract.stage.upper(),
                        contract.script_content,
                        contract.docker_image,
                        validated_cpu,
                        validated_mem,
                        created_by,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                row["pipeline_id"] = str(row["pipeline_id"])
                return PipelineResponseContract(**row)
        except psycopg2.IntegrityError as e:
            conn.rollback()
            raise ValueError(f"Pipeline '{contract.name}' already exists in project '{project_id}': {e}")
        finally:
            conn.close()

    def get_pipeline(self, project_id: str, identifier: str) -> Optional[PipelineResponseContract]:
        """Retrieves pipeline by UUID or unique name within project."""
        query_by_id = """
            SELECT pipeline_id, project_id, name, description, stage, docker_image,
                   default_cpu_limit, default_memory_limit, version, created_by, created_at, updated_at
            FROM project_pipelines
            WHERE project_id = %s AND (pipeline_id::text = %s OR name = %s);
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(query_by_id, (project_id, identifier, identifier))
                row = cur.fetchone()
                if row:
                    row["pipeline_id"] = str(row["pipeline_id"])
                    return PipelineResponseContract(**row)
                return None
        finally:
            conn.close()

    def get_pipeline_script(self, project_id: str, identifier: str) -> Optional[str]:
        """Retrieves full script content for execution."""
        query = """
            SELECT script_content FROM project_pipelines
            WHERE project_id = %s AND (pipeline_id::text = %s OR name = %s);
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(query, (project_id, identifier, identifier))
                row = cur.fetchone()
                return row["script_content"] if row else None
        finally:
            conn.close()

    def list_pipelines(self, project_id: str) -> List[PipelineResponseContract]:
        """Lists all registered pipelines for a project."""
        query = """
            SELECT pipeline_id, project_id, name, description, stage, docker_image,
                   default_cpu_limit, default_memory_limit, version, created_by, created_at, updated_at
            FROM project_pipelines
            WHERE project_id = %s
            ORDER BY created_at DESC;
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(query, (project_id,))
                rows = cur.fetchall()
                results = []
                for r in rows:
                    r["pipeline_id"] = str(r["pipeline_id"])
                    results.append(PipelineResponseContract(**r))
                return results
        finally:
            conn.close()

    def update_pipeline(
        self,
        project_id: str,
        identifier: str,
        contract: PipelineUpdateContract,
    ) -> PipelineResponseContract:
        """Updates pipeline fields, validating script or resource limits if changed and bumping version."""
        existing = self.get_pipeline(project_id, identifier)
        if not existing:
            raise ValueError(f"Pipeline '{identifier}' not found in project '{project_id}'.")

        validated_cpu, validated_mem = validate_pipeline_default_resources(
            default_cpu_limit=contract.default_cpu_limit,
            default_memory_limit=contract.default_memory_limit,
        )

        updates = []
        params: List[Any] = []

        if contract.name:
            updates.append("name = %s")
            params.append(contract.name)
        if contract.description is not None:
            updates.append("description = %s")
            params.append(contract.description)
        if contract.stage:
            updates.append("stage = %s")
            params.append(contract.stage.upper())
        if contract.docker_image:
            updates.append("docker_image = %s")
            params.append(contract.docker_image)
        if validated_cpu is not None:
            updates.append("default_cpu_limit = %s")
            params.append(validated_cpu)
        if validated_mem is not None:
            updates.append("default_memory_limit = %s")
            params.append(validated_mem)
        if contract.script_content:
            is_valid, err = validate_python_script(contract.script_content)
            if not is_valid:
                raise ValueError(f"Invalid script syntax: {err}")
            updates.append("script_content = %s")
            params.append(contract.script_content)
            updates.append("version = version + 1")

        if not updates:
            return existing

        updates.append("updated_at = NOW()")
        set_clause = ", ".join(updates)
        params.extend([project_id, existing.pipeline_id])

        query = f"""
            UPDATE project_pipelines
            SET {set_clause}
            WHERE project_id = %s AND pipeline_id = %s
            RETURNING pipeline_id, project_id, name, description, stage, docker_image,
                      default_cpu_limit, default_memory_limit, version, created_by, created_at, updated_at;
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(query, tuple(params))
                row = cur.fetchone()
                conn.commit()
                row["pipeline_id"] = str(row["pipeline_id"])
                return PipelineResponseContract(**row)
        finally:
            conn.close()

    def delete_pipeline(self, project_id: str, identifier: str) -> bool:
        """Deletes a pipeline from a project."""
        query = """
            DELETE FROM project_pipelines
            WHERE project_id = %s AND (pipeline_id::text = %s OR name = %s)
            RETURNING pipeline_id;
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(query, (project_id, identifier, identifier))
                row = cur.fetchone()
                conn.commit()
                return bool(row)
        finally:
            conn.close()

    def create_run_record(
        self,
        project_id: str,
        pipeline_id: str,
        stage: str,
        target_tier: str,
        target_dataset: str,
        input_datasets: List[str],
        details: Optional[Dict[str, Any]] = None,
    ) -> PipelineRunResponseContract:
        """Initializes a new execution run audit record."""
        query = """
            INSERT INTO project_pipeline_runs (
                project_id, pipeline_id, status, stage, target_tier, input_datasets, target_dataset,
                records_processed, details, started_at
            )
            VALUES (%s, %s, 'RUNNING', %s, %s, %s, %s, 0, %s, NOW())
            RETURNING run_id, project_id, pipeline_id, status, stage, target_tier, target_dataset,
                      records_processed, exit_code, logs, details, started_at, completed_at;
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    query,
                    (
                        project_id,
                        pipeline_id,
                        stage,
                        target_tier.upper(),
                        Json(input_datasets),
                        target_dataset,
                        Json(details or {}),
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return self._hydrate_run_row(row, duration_ms=0)
        finally:
            conn.close()

    def complete_run_record(
        self,
        run_id: str,
        status: str,
        records_processed: int,
        duration_ms: int,
        exit_code: int,
        logs: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> PipelineRunResponseContract:
        """Finalizes an execution run audit record with exit status, resource details, and logs."""
        query = """
            UPDATE project_pipeline_runs
            SET status = %s,
                records_processed = %s,
                exit_code = %s,
                logs = %s,
                details = %s,
                completed_at = NOW()
            WHERE run_id = %s
            RETURNING run_id, project_id, pipeline_id, status, stage, target_tier, target_dataset,
                      records_processed, exit_code, logs, details, started_at, completed_at;
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    query,
                    (
                        status,
                        records_processed,
                        exit_code,
                        logs,
                        Json(details or {}),
                        run_id,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return self._hydrate_run_row(row, duration_ms=duration_ms)
        finally:
            conn.close()

    def list_runs(self, project_id: str, pipeline_id: Optional[str] = None) -> List[PipelineRunResponseContract]:
        """Lists historical pipeline execution runs for audit and observability."""
        if pipeline_id:
            query = """
                SELECT run_id, project_id, pipeline_id, status, stage, target_tier, target_dataset,
                       records_processed, exit_code, logs, details, started_at, completed_at
                FROM project_pipeline_runs
                WHERE project_id = %s AND (pipeline_id::text = %s)
                ORDER BY started_at DESC;
            """
            params = (project_id, pipeline_id)
        else:
            query = """
                SELECT run_id, project_id, pipeline_id, status, stage, target_tier, target_dataset,
                       records_processed, exit_code, logs, details, started_at, completed_at
                FROM project_pipeline_runs
                WHERE project_id = %s
                ORDER BY started_at DESC;
            """
            params = (project_id,)

        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(query, params)
                rows = cur.fetchall()
                results = []
                for r in rows:
                    duration_ms = 0
                    if r.get("completed_at") and r.get("started_at"):
                        duration_ms = int((r["completed_at"] - r["started_at"]).total_seconds() * 1000)
                    results.append(self._hydrate_run_row(r, duration_ms=max(0, duration_ms)))
                return results
        finally:
            conn.close()
