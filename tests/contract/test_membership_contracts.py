import json
from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient
from click.testing import CliRunner

from src.api import app
from src.security.jwt import create_access_token
from src.cli.main import cli
from src.domains.project.models.contract.membership import MemberContract

client = TestClient(app)


def test_list_members_unauthenticated():
    response = client.get("/api/v1/projects/proj-alpha/members")
    assert response.status_code == 401


def test_list_members_non_member_404():
    token = create_access_token(subject="stranger", username="stranger", roles=["user"])
    headers = {"Authorization": f"Bearer {token}"}

    with patch("src.domains.project.operations.membership.ProjectMembershipService.is_member", return_value=False):
        response = client.get("/api/v1/projects/proj-alpha/members", headers=headers)
        assert response.status_code == 404
        assert "not found or access denied" in response.json()["detail"]


def test_list_members_member_success():
    token = create_access_token(subject="alice", username="alice", roles=["user"])
    headers = {"Authorization": f"Bearer {token}"}

    members = [
        MemberContract(
            project_id="proj-alpha",
            user_id="alice",
            role="owner",
            added_by="admin",
            added_at="2026-10-19T20:00:00Z",
        )
    ]

    with patch("src.domains.project.operations.membership.ProjectMembershipService.is_member", return_value=True):
        with patch("src.domains.project.operations.membership.ProjectMembershipService.list_members", return_value=members):
            response = client.get("/api/v1/projects/proj-alpha/members", headers=headers)
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["user_id"] == "alice"
            assert data[0]["role"] == "owner"


def test_add_member_non_owner_forbidden():
    token = create_access_token(subject="bob", username="bob", roles=["user"])
    headers = {"Authorization": f"Bearer {token}"}

    with patch("src.domains.project.operations.membership.ProjectMembershipService.is_owner", return_value=False):
        response = client.post(
            "/api/v1/projects/proj-alpha/members",
            json={"user_id": "charlie", "role": "member"},
            headers=headers,
        )
        assert response.status_code == 403


def test_add_member_owner_success():
    token = create_access_token(subject="alice", username="alice", roles=["user"])
    headers = {"Authorization": f"Bearer {token}"}

    new_member = MemberContract(
        project_id="proj-alpha",
        user_id="charlie",
        role="member",
        added_by="alice",
        added_at="2026-10-19T20:05:00Z",
    )

    with patch("src.domains.project.operations.membership.ProjectMembershipService.is_owner", return_value=True):
        with patch("src.domains.project.operations.membership.ProjectMembershipService.add_member", return_value=new_member):
            response = client.post(
                "/api/v1/projects/proj-alpha/members",
                json={"user_id": "charlie", "role": "member"},
                headers=headers,
            )
            assert response.status_code == 201
            assert response.json()["user_id"] == "charlie"


def test_remove_member_last_owner_conflict():
    token = create_access_token(subject="alice", username="alice", roles=["user"])
    headers = {"Authorization": f"Bearer {token}"}

    with patch("src.domains.project.operations.membership.ProjectMembershipService.is_owner", return_value=True):
        with patch("src.domains.project.operations.membership.ProjectMembershipService.remove_member", side_effect=ValueError("Cannot remove the last owner")):
            response = client.delete("/api/v1/projects/proj-alpha/members/alice", headers=headers)
            assert response.status_code == 409
            assert "Cannot remove the last owner" in response.json()["detail"]


def test_remove_member_success():
    token = create_access_token(subject="alice", username="alice", roles=["user"])
    headers = {"Authorization": f"Bearer {token}"}

    with patch("src.domains.project.operations.membership.ProjectMembershipService.is_owner", return_value=True):
        with patch("src.domains.project.operations.membership.ProjectMembershipService.remove_member", return_value=True):
            response = client.delete("/api/v1/projects/proj-alpha/members/bob", headers=headers)
            assert response.status_code == 204


def test_cli_project_members_commands():
    runner = CliRunner()
    members = [
        MemberContract(
            project_id="proj-alpha",
            user_id="alice",
            role="owner",
            added_by="admin",
            added_at="2026-10-19T20:00:00Z",
        )
    ]

    # CLI list
    with patch("src.domains.project.operations.membership.ProjectMembershipService.is_member", return_value=True):
        with patch("src.domains.project.operations.membership.ProjectMembershipService.list_members", return_value=members):
            res = runner.invoke(cli, ["project", "members", "list", "proj-alpha"])
            assert res.exit_code == 0
            assert "=== Members of proj-alpha ===" in res.output
            assert "alice" in res.output

            res_json = runner.invoke(cli, ["project", "members", "list", "proj-alpha", "--json"])
            assert res_json.exit_code == 0
            assert json.loads(res_json.output)[0]["user_id"] == "alice"
