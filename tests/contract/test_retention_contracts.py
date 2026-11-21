import json
from datetime import datetime, timezone
from unittest.mock import patch, AsyncMock
import pytest
from fastapi.testclient import TestClient
from click.testing import CliRunner

from src.api import app
from src.security.jwt import create_access_token
from src.cli.main import cli
from src.domains.retention.models.contract.retention import (
    TTLPolicyContract,
    DatasetTTLSetRequestContract,
    ProjectTTLDefaultsRequestContract,
    DatasetRetentionStateContract,
    QueryDataArtifactContract,
    RetentionHoldRequestContract,
    DatasetRestoreRequestContract,
    ProjectRetentionSummaryContract,
    CleanupTriggerRequestContract,
    CleanupJobRunContract,
    LineageTombstoneContract,
)

client = TestClient(app)


def _sample_retention_state(**overrides) -> DatasetRetentionStateContract:
    now = datetime(2026, 11, 21, 10, 0, 0, tzinfo=timezone.utc)
    base = {
        "project_id": "alpha-corp",
        "dataset_id": "system_stats",
        "tier": "BRONZE",
        "policy_source": "DATASET_EXPLICIT",
        "effective_ttl_expression": "30d",
        "effective_ttl_seconds": 2592000,
        "granularity": "INGESTION_AGE",
        "timestamp_column": None,
        "grace_period_expression": "24h",
        "grace_period_seconds": 86400,
        "reference_timestamp": now,
        "expires_at": datetime(2026, 12, 21, 10, 0, 0, tzinfo=timezone.utc),
        "retention_hold": False,
        "lifecycle_status": "ACTIVE",
        "active_partitions_count": 1,
        "auto_restored": False,
    }
    base.update(overrides)
    return DatasetRetentionStateContract(**base)


def test_pydantic_contract_validation_rules():
    # Valid dataset TTL request
    req = DatasetTTLSetRequestContract(
        tier="bronze",
        ttl_expression="30d",
        granularity="TIMESTAMP_COLUMN",
        timestamp_column="event_ts",
        grace_period_expression="0h",
    )
    assert req.tier == "BRONZE"
    assert req.grace_period_expression == "0h"

    # Missing timestamp_column when granularity is TIMESTAMP_COLUMN must fail
    with pytest.raises(ValueError, match="timestamp_column is required"):
        DatasetTTLSetRequestContract(
            tier="BRONZE",
            ttl_expression="7d",
            granularity="TIMESTAMP_COLUMN",
        )

    # Zero or negative TTL expression must fail
    with pytest.raises(ValueError):
        DatasetTTLSetRequestContract(tier="BRONZE", ttl_expression="0h")
    with pytest.raises(ValueError):
        DatasetTTLSetRequestContract(tier="BRONZE", ttl_expression="-5d")

    # Restore contract requires either ttl_expression or retention_hold=True
    with pytest.raises(ValueError, match="requires either extending"):
        DatasetRestoreRequestContract(tier="BRONZE", ttl_expression=None, retention_hold=False)


def test_api_dataset_ttl_crud_endpoints():
    token = create_access_token(subject="alice", username="alice", roles=["admin"])
    headers = {"Authorization": f"Bearer {token}"}
    mock_state = _sample_retention_state()

    with patch(
        "src.domains.retention.facade.retention.RetentionFacade.set_dataset_ttl",
        new_callable=AsyncMock,
        return_value=mock_state,
    ):
        resp = client.put(
            "/api/v1/projects/alpha-corp/datasets/system_stats/ttl",
            headers=headers,
            json={"tier": "BRONZE", "ttl_expression": "30d", "granularity": "INGESTION_AGE"},
        )
        assert resp.status_code == 200
        assert resp.json()["effective_ttl_expression"] == "30d"

    with patch(
        "src.domains.retention.facade.retention.RetentionFacade.get_dataset_ttl",
        new_callable=AsyncMock,
        return_value=mock_state,
    ):
        resp = client.get("/api/v1/projects/alpha-corp/datasets/system_stats/ttl?tier=BRONZE", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["dataset_id"] == "system_stats"

    with patch(
        "src.domains.retention.facade.retention.RetentionFacade.clear_dataset_ttl",
        new_callable=AsyncMock,
        return_value=_sample_retention_state(policy_source="TIER_DEFAULT"),
    ):
        resp = client.delete("/api/v1/projects/alpha-corp/datasets/system_stats/ttl?tier=BRONZE", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["policy_source"] == "TIER_DEFAULT"


def test_api_hold_restore_summary_and_cleanup_endpoints():
    token = create_access_token(subject="alice", username="alice", roles=["admin"])
    headers = {"Authorization": f"Bearer {token}"}

    held_state = _sample_retention_state(retention_hold=True, lifecycle_status="HELD", hold_reason="Incident")
    with patch(
        "src.domains.retention.facade.retention.RetentionFacade.set_dataset_hold",
        new_callable=AsyncMock,
        return_value=held_state,
    ):
        resp = client.put(
            "/api/v1/projects/alpha-corp/datasets/system_stats/hold",
            headers=headers,
            json={"tier": "BRONZE", "retention_hold": True, "reason": "Incident"},
        )
        assert resp.status_code == 200
        assert resp.json()["retention_hold"] is True
        assert resp.json()["lifecycle_status"] == "HELD"

    restored_state = _sample_retention_state(effective_ttl_expression="60d", auto_restored=True)
    with patch(
        "src.domains.retention.facade.retention.RetentionFacade.restore_dataset",
        new_callable=AsyncMock,
        return_value=restored_state,
    ):
        resp = client.post(
            "/api/v1/projects/alpha-corp/datasets/system_stats/ttl/restore",
            headers=headers,
            json={"tier": "BRONZE", "ttl_expression": "60d"},
        )
        assert resp.status_code == 200
        assert resp.json()["auto_restored"] is True

    mock_summary = ProjectRetentionSummaryContract(
        project_id="alpha-corp",
        default_policies={"BRONZE": "30d", "SILVER": "90d", "GOLD": "365d"},
        counts={"active": 2, "expiring_within_24h": 1, "held": 0, "soft_deleted": 0, "purged_tombstones": 1},
        datasets=[],
        query_artifacts_summary={"active_caches": 3, "materialized_exports": 1, "query_history_logs": 10, "total_size_bytes": 4096},
    )
    with patch(
        "src.domains.retention.facade.retention.RetentionFacade.get_project_summary",
        new_callable=AsyncMock,
        return_value=mock_summary,
    ):
        resp = client.get("/api/v1/projects/alpha-corp/ttl/summary", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["counts"]["active"] == 2

    mock_run = CleanupJobRunContract(
        run_id="run-123",
        trigger_type="DRY_RUN",
        project_id="alpha-corp",
        initiated_by="alice",
        status="SUCCESS",
        datasets_evaluated=5,
        datasets_purged=1,
        bytes_reclaimed=1048576,
        started_at=datetime.now(timezone.utc),
        duration_ms=42,
    )
    with patch(
        "src.domains.retention.facade.retention.RetentionFacade.trigger_cleanup",
        new_callable=AsyncMock,
        return_value=mock_run,
    ):
        resp = client.post(
            "/api/v1/projects/alpha-corp/ttl/cleanup",
            headers=headers,
            json={"dry_run": True},
        )
        assert resp.status_code == 200
        assert resp.json()["trigger_type"] == "DRY_RUN"
        assert resp.json()["bytes_reclaimed"] == 1048576


def test_cli_project_ttl_commands():
    runner = CliRunner()
    mock_state = _sample_retention_state()

    with patch(
        "src.domains.retention.facade.retention.RetentionFacade.set_dataset_ttl",
        new_callable=AsyncMock,
        return_value=mock_state,
    ):
        res = runner.invoke(
            cli,
            ["project", "ttl", "set", "--project", "alpha-corp", "--dataset", "system_stats", "--ttl", "30d", "--json"],
        )
        assert res.exit_code == 0
        parsed = json.loads(res.output)
        assert parsed["effective_ttl_expression"] == "30d"

    with patch(
        "src.domains.retention.facade.retention.RetentionFacade.get_dataset_ttl",
        new_callable=AsyncMock,
        return_value=mock_state,
    ):
        res = runner.invoke(
            cli,
            ["project", "ttl", "get", "--project", "alpha-corp", "--dataset", "system_stats"],
        )
        assert res.exit_code == 0
        assert "Effective TTL: 30d" in res.output

    mock_run = CleanupJobRunContract(
        run_id="run-456",
        trigger_type="DRY_RUN",
        project_id="alpha-corp",
        initiated_by="admin",
        status="SUCCESS",
        datasets_evaluated=3,
        datasets_purged=1,
        bytes_reclaimed=2048,
        started_at=datetime.now(timezone.utc),
        duration_ms=15,
    )
    with patch(
        "src.domains.retention.facade.retention.RetentionFacade.trigger_cleanup",
        new_callable=AsyncMock,
        return_value=mock_run,
    ):
        res = runner.invoke(
            cli,
            ["project", "ttl", "cleanup", "--project", "alpha-corp", "--dry-run", "--json"],
        )
        assert res.exit_code == 0
        parsed = json.loads(res.output)
        assert parsed["trigger_type"] == "DRY_RUN"
        assert parsed["bytes_reclaimed"] == 2048
