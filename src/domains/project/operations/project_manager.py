import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
import psycopg2
from psycopg2.extras import RealDictCursor

try:
    from src.config.settings import settings
    from src.domains.project.models.contract.project import (
        ProjectCreateContract,
        ProjectResponseContract,
        ProjectDatasetContract,
    )
except ImportError:
    from config.settings import settings
    from domains.project.models.contract.project import (
        ProjectCreateContract,
        ProjectResponseContract,
        ProjectDatasetContract,
    )

logger = logging.getLogger("artemis.project.manager")


class ProjectManager:
    """Manages Project metadata and dataset catalog persistence in PostgreSQL."""

    def __init__(self):
        self.host = settings.postgres_host
        self.port = settings.postgres_port
        self.dbname = settings.postgres_db
        self.user = settings.postgres_user
        self.password = settings.postgres_password

    def _get_connection(self):
        return psycopg2.connect(
            host=self.host,
            port=self.port,
            dbname=self.dbname,
            user=self.user,
            password=self.password,
            cursor_factory=RealDictCursor,
        )

    def create_project(self, project: ProjectCreateContract, creator_user_id: Optional[str] = None) -> ProjectResponseContract:
        """Creates a new project record in PostgreSQL and assigns creator as owner."""
        query = """
            INSERT INTO projects (project_id, name, description, status, created_at, updated_at)
            VALUES (%s, %s, %s, 'ACTIVE', NOW(), NOW())
            RETURNING project_id, name, description, status, created_at, updated_at;
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(query, (project.project_id, project.name, project.description))
                row = cur.fetchone()

                owner_id = creator_user_id or "admin"
                member_query = """
                    INSERT INTO project_members (project_id, user_id, role, added_by, added_at)
                    VALUES (%s, %s, 'owner', %s, NOW())
                    ON CONFLICT (project_id, user_id) DO UPDATE SET role = 'owner';
                """
                try:
                    cur.execute(member_query, (project.project_id, owner_id, owner_id))
                except Exception as me:
                    logger.warning(f"Could not insert project owner: {me}")

                conn.commit()
                return ProjectResponseContract(**row)
        except psycopg2.IntegrityError as e:
            conn.rollback()
            raise ValueError(f"Project '{project.project_id}' already exists or violates constraint: {e}")
        finally:
            conn.close()

    def get_project(self, project_id: str) -> Optional[ProjectResponseContract]:
        """Fetches project by project_id."""
        query = "SELECT project_id, name, description, status, created_at, updated_at FROM projects WHERE project_id = %s;"
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(query, (project_id,))
                row = cur.fetchone()
                if row:
                    return ProjectResponseContract(**row)
                return None
        finally:
            conn.close()

    def list_projects(self) -> List[ProjectResponseContract]:
        """Lists all projects ordered by creation time."""
        query = "SELECT project_id, name, description, status, created_at, updated_at FROM projects ORDER BY created_at DESC;"
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(query)
                rows = cur.fetchall()
                return [ProjectResponseContract(**r) for r in rows]
        finally:
            conn.close()

    def delete_project(self, project_id: str) -> bool:
        """Deletes a project and cascades associated datasets and pipelines."""
        query = "DELETE FROM projects WHERE project_id = %s RETURNING project_id;"
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                try:
                    cur.execute("DELETE FROM project_members WHERE project_id = %s;", (project_id,))
                except Exception:
                    pass
                cur.execute(query, (project_id,))
                row = cur.fetchone()
                conn.commit()

                # Clean up KDG knowledge graph subtree for this project
                try:
                    from src.domains.discovery.operations.kdg_graph_store import KDGGraphStore
                    KDGGraphStore().delete_workspace_subtree(project_id)
                except Exception:
                    pass

                return bool(row)
        finally:
            conn.close()

    def record_dataset(
        self,
        project_id: str,
        dataset_id: str,
        tier: str,
        dataset_type: str,
        storage_uri: str,
        size_bytes: int,
        record_count: int,
    ) -> ProjectDatasetContract:
        """Upserts a dataset registration in the project catalog."""
        query = """
            INSERT INTO project_datasets (
                project_id, dataset_id, tier, dataset_type, storage_uri, size_bytes, record_count, last_modified
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (project_id, dataset_id, tier)
            DO UPDATE SET
                storage_uri = EXCLUDED.storage_uri,
                size_bytes = EXCLUDED.size_bytes,
                record_count = EXCLUDED.record_count,
                last_modified = NOW()
            RETURNING project_id, dataset_id, tier, dataset_type, storage_uri, size_bytes, record_count, last_modified;
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(query, (project_id, dataset_id, tier.upper(), dataset_type.upper(), storage_uri, size_bytes, record_count))
                row = cur.fetchone()
                conn.commit()
                return ProjectDatasetContract(**row)
        finally:
            conn.close()

    def list_datasets(self, project_id: str, tier: Optional[str] = None) -> List[ProjectDatasetContract]:
        """Lists registered datasets for a project."""
        if tier:
            query = "SELECT * FROM project_datasets WHERE project_id = %s AND tier = %s ORDER BY last_modified DESC;"
            params = (project_id, tier.upper())
        else:
            query = "SELECT * FROM project_datasets WHERE project_id = %s ORDER BY tier, last_modified DESC;"
            params = (project_id,)

        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(query, params)
                rows = cur.fetchall()
                return [ProjectDatasetContract(**r) for r in rows]
        finally:
            conn.close()
