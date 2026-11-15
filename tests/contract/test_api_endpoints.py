import pytest
from fastapi.testclient import TestClient
from src.api import app
from src.security.jwt import create_access_token

client = TestClient(app)


def test_health_check_public():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "HEALTHY"


def test_auth_token_success():
    response = client.post("/api/v1/auth/token", json={"username": "admin", "password": "admin"})
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "Bearer"
    assert data["expires_in"] == 86400


def test_auth_token_failure():
    response = client.post("/api/v1/auth/token", json={"username": "admin", "password": "wrong_password"})
    assert response.status_code == 401


def test_protected_endpoint_without_token():
    response = client.post("/api/v1/analytics/query", json={"sql": "SELECT 1"})
    assert response.status_code == 401


def test_protected_endpoint_with_invalid_token():
    headers = {"Authorization": "Bearer invalid_garbage_token"}
    response = client.post("/api/v1/analytics/query", json={"sql": "SELECT 1"}, headers=headers)
    assert response.status_code == 401


def test_analytics_query_with_valid_token():
    token = create_access_token(subject="admin", username="admin", roles=["admin"])
    headers = {"Authorization": f"Bearer {token}"}
    response = client.post(
        "/api/v1/analytics/query",
        json={"sql": "SELECT 42 as answer", "format": "json"},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert "columns" in data or "formatted_output" in data


def test_graph_endpoints_with_valid_token():
    token = create_access_token(subject="admin", username="admin", roles=["admin"])
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get(
        "/api/v1/graph/related?term=test_ip",
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["query_term"] == "test_ip"
    assert "entities" in data
