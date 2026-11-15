from unittest.mock import MagicMock, patch
import pytest
from src.domains.project.operations.membership import ProjectMembershipService


@pytest.fixture
def mock_db():
    with patch("psycopg2.connect") as mock_connect:
        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cursor
        conn.__enter__.return_value = conn
        mock_connect.return_value = conn
        yield conn, cursor


def test_add_member_valid(mock_db):
    conn, cursor = mock_db
    cursor.fetchone.return_value = {
        "project_id": "proj-1",
        "user_id": "user-alice",
        "role": "owner",
        "added_by": "admin",
        "added_at": "2026-10-19T20:00:00Z",
    }
    svc = ProjectMembershipService()
    member = svc.add_member("proj-1", "user-alice", role="owner", added_by="admin")

    assert member.project_id == "proj-1"
    assert member.user_id == "user-alice"
    assert member.role == "owner"


def test_add_member_invalid_role(mock_db):
    svc = ProjectMembershipService()
    with pytest.raises(ValueError, match="Invalid role 'invalid'"):
        svc.add_member("proj-1", "user-bob", role="invalid")


def test_remove_member_last_owner_protection(mock_db):
    conn, cursor = mock_db
    # First fetchone checks role -> 'owner'
    # Second fetchone checks owner count -> 1
    cursor.fetchone.side_effect = [
        {"role": "owner"},
        {"count": 1},
    ]

    svc = ProjectMembershipService()
    with pytest.raises(ValueError, match="Cannot remove the last owner"):
        svc.remove_member("proj-1", "user-alice")


def test_remove_member_multiple_owners_success(mock_db):
    conn, cursor = mock_db
    cursor.fetchone.side_effect = [
        {"role": "owner"},
        {"count": 2},
    ]

    svc = ProjectMembershipService()
    assert svc.remove_member("proj-1", "user-alice") is True


def test_remove_regular_member_success(mock_db):
    conn, cursor = mock_db
    cursor.fetchone.side_effect = [
        {"role": "member"},
    ]

    svc = ProjectMembershipService()
    assert svc.remove_member("proj-1", "user-bob") is True


def test_remove_nonexistent_member(mock_db):
    conn, cursor = mock_db
    cursor.fetchone.return_value = None

    svc = ProjectMembershipService()
    assert svc.remove_member("proj-1", "unknown") is False


def test_is_member_and_is_owner(mock_db):
    conn, cursor = mock_db
    cursor.fetchone.side_effect = [{"?column?": 1}, None]

    svc = ProjectMembershipService()
    # Member exists
    assert svc.is_member("proj-1", "user-alice") is True
    # Not member
    assert svc.is_member("proj-1", "user-stranger") is False


def test_admin_role_bypass(mock_db):
    conn, cursor = mock_db
    svc = ProjectMembershipService()

    # Admin bypasses table query completely for is_member
    assert svc.is_member("proj-1", "any-user", user_roles=["admin"]) is True
    assert svc.is_owner("proj-1", "any-user", user_roles=["admin"]) is True

    # Admin list_member_projects queries all projects
    cursor.fetchall.return_value = [{"project_id": "proj-1"}, {"project_id": "proj-2"}]
    all_projects = svc.list_member_projects("admin-user", user_roles=["admin"])
    assert all_projects == ["proj-1", "proj-2"]


def test_regular_user_list_member_projects(mock_db):
    conn, cursor = mock_db
    cursor.fetchall.return_value = [{"project_id": "proj-alpha"}]

    svc = ProjectMembershipService()
    projects = svc.list_member_projects("alice", user_roles=["user"])
    assert projects == ["proj-alpha"]


def test_anonymous_user_empty(mock_db):
    svc = ProjectMembershipService()
    assert svc.is_member("proj-1", None) is False
    assert svc.is_owner("proj-1", None) is False
    assert svc.list_member_projects(None) == []
