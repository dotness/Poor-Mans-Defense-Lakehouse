import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
import psycopg2
from psycopg2.extras import RealDictCursor

try:
    from src.config.settings import settings
    from src.domains.project.models.contract.membership import MemberContract
except ImportError:
    from config.settings import settings
    from domains.project.models.contract.membership import MemberContract

logger = logging.getLogger("artemis.project.membership")


class ProjectMembershipService:
    """Manages project memberships, roles (owner, member), and access evaluation."""

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
        """Ensures project_members table exists."""
        query = """
        CREATE TABLE IF NOT EXISTS project_members (
            project_id VARCHAR(64) NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
            user_id VARCHAR(64) NOT NULL,
            role VARCHAR(20) NOT NULL DEFAULT 'member',
            added_by VARCHAR(64) NOT NULL DEFAULT 'admin',
            added_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (project_id, user_id)
        );
        CREATE INDEX IF NOT EXISTS idx_project_members_user ON project_members(user_id);
        CREATE INDEX IF NOT EXISTS idx_project_members_project ON project_members(project_id);
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query)
                conn.commit()
        except Exception as e:
            logger.warning(f"Could not ensure project_members table: {e}")

    def add_member(
        self,
        project_id: str,
        user_id: str,
        role: str = "member",
        added_by: str = "admin",
    ) -> MemberContract:
        """Adds or updates a member's role in a project."""
        role_norm = role.lower()
        if role_norm not in ("owner", "member"):
            raise ValueError(f"Invalid role '{role}'. Must be 'owner' or 'member'.")

        query = """
            INSERT INTO project_members (project_id, user_id, role, added_by, added_at)
            VALUES (%s, %s, %s, %s, NOW())
            ON CONFLICT (project_id, user_id)
            DO UPDATE SET role = EXCLUDED.role, added_by = EXCLUDED.added_by, added_at = NOW()
            RETURNING project_id, user_id, role, added_by, added_at;
        """
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (project_id, user_id, role_norm, added_by))
                row = cur.fetchone()
                conn.commit()
                return MemberContract(**row)

    def remove_member(self, project_id: str, user_id: str) -> bool:
        """Removes a member from a project with last-owner protection."""
        check_query = """
            SELECT role FROM project_members
            WHERE project_id = %s AND user_id = %s;
        """
        owner_count_query = """
            SELECT COUNT(*) AS count FROM project_members
            WHERE project_id = %s AND role = 'owner';
        """
        delete_query = """
            DELETE FROM project_members
            WHERE project_id = %s AND user_id = %s;
        """
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(check_query, (project_id, user_id))
                member = cur.fetchone()
                if not member:
                    return False

                if member["role"] == "owner":
                    cur.execute(owner_count_query, (project_id,))
                    owner_count = cur.fetchone()["count"]
                    if owner_count <= 1:
                        raise ValueError("Cannot remove the last owner of a project.")

                cur.execute(delete_query, (project_id, user_id))
                conn.commit()
                return True

    def list_members(self, project_id: str) -> List[MemberContract]:
        """Lists all members of a project."""
        query = """
            SELECT project_id, user_id, role, added_by, added_at
            FROM project_members
            WHERE project_id = %s
            ORDER BY added_at ASC;
        """
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (project_id,))
                rows = cur.fetchall()
                return [MemberContract(**r) for r in rows]

    def get_member(self, project_id: str, user_id: str) -> Optional[MemberContract]:
        """Gets member details if present."""
        query = """
            SELECT project_id, user_id, role, added_by, added_at
            FROM project_members
            WHERE project_id = %s AND user_id = %s;
        """
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (project_id, user_id))
                row = cur.fetchone()
                if row:
                    return MemberContract(**row)
                return None

    def is_member(
        self,
        project_id: str,
        user_id: Optional[str],
        user_roles: Optional[List[str]] = None,
    ) -> bool:
        """Evaluates whether user has membership in project, with admin role bypass."""
        if user_roles and "admin" in user_roles:
            return True

        if not user_id:
            return False

        query = """
            SELECT 1 FROM project_members
            WHERE project_id = %s AND user_id = %s;
        """
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (project_id, user_id))
                return cur.fetchone() is not None

    def is_owner(
        self,
        project_id: str,
        user_id: Optional[str],
        user_roles: Optional[List[str]] = None,
    ) -> bool:
        """Evaluates whether user is an owner of the project, with admin role bypass."""
        if user_roles and "admin" in user_roles:
            return True

        if not user_id:
            return False

        query = """
            SELECT 1 FROM project_members
            WHERE project_id = %s AND user_id = %s AND role = 'owner';
        """
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (project_id, user_id))
                return cur.fetchone() is not None

    def list_member_projects(
        self,
        user_id: Optional[str],
        user_roles: Optional[List[str]] = None,
    ) -> List[str]:
        """Returns all project_ids that the user is a member of (all projects if admin)."""
        if user_roles and "admin" in user_roles:
            query = "SELECT project_id FROM projects ORDER BY project_id ASC;"
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query)
                    return [r["project_id"] for r in cur.fetchall()]

        if not user_id:
            return []

        query = """
            SELECT project_id FROM project_members
            WHERE user_id = %s
            ORDER BY project_id ASC;
        """
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (user_id,))
                return [r["project_id"] for r in cur.fetchall()]
