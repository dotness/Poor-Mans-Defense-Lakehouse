import json
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from click.testing import CliRunner
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.domains.pipeline.models.contract.project_pipeline import (
    PipelineCreateContract,
    PipelineUpdateContract,
    PipelineResponseContract,
    PipelineRunTriggerContract,
    PipelineRunResponseContract,
)
from src.domains.pipeline.operations.script_validator import validate_python_script
from src.domains.pipeline.api.routes import router as pipeline_router
from src.cli.commands.project import project_group


def test_script_validator_valid():
    script = "import pandas as pd\nprint('hello')\n"
    is_valid, err = validate_python_script(script)
    assert is_valid is True
    assert err == ""


def test_script_validator_syntax_error():
    script = "def broken_code(: print('error')"
    is_valid, err = validate_python_script(script)
    assert is_valid is False
    assert "SyntaxError" in err


def test_script_validator_empty():
    is_valid, err = validate_python_script("")
    assert is_valid is False
    assert "empty" in err


def test_pipeline_create_contract():
    contract = PipelineCreateContract(
        name="Cleanse Logs",
        description="Filter high CPU",
        stage="BRONZE_TO_SILVER",
        script_content="import pyarrow as pa\n",
        default_cpu_limit=1.5,
        default_memory_limit="1g",
    )
    assert contract.name == "Cleanse Logs"
    assert contract.stage == "BRONZE_TO_SILVER"
    assert contract.docker_image == "artemis-pipeline-runner:latest"
    assert contract.default_cpu_limit == 1.5
    assert contract.default_memory_limit == "1g"


def test_pipeline_update_and_response_contracts():
    upd = PipelineUpdateContract(
        default_cpu_limit=2.5,
        default_memory_limit="2048m",
    )
    assert upd.default_cpu_limit == 2.5
    assert upd.default_memory_limit == "2048m"

    now = datetime.now(timezone.utc)
    resp = PipelineResponseContract(
        pipeline_id="pipe-123",
        project_id="proj-alpha",
        name="Cleanse Logs",
        stage="BRONZE_TO_SILVER",
        docker_image="artemis-pipeline-runner:latest",
        default_cpu_limit=2.5,
        default_memory_limit="2048m",
        version=2,
        created_by="admin",
        created_at=now,
        updated_at=now,
    )
    assert resp.default_cpu_limit == 2.5
    assert resp.default_memory_limit == "2048m"


def test_pipeline_run_trigger_and_response_contracts():
    trigger = PipelineRunTriggerContract(
        input_datasets=["raw_metrics"],
        target_dataset="clean_metrics",
        target_tier="SILVER",
        timeout_seconds=120,
        cpu_limit=3.0,
        memory_limit="3g",
    )
    assert trigger.target_dataset == "clean_metrics"
    assert trigger.target_tier == "SILVER"
    assert trigger.timeout_seconds == 120
    assert trigger.cpu_limit == 3.0
    assert trigger.memory_limit == "3g"

    now = datetime.now(timezone.utc)
    run_resp = PipelineRunResponseContract(
        run_id="run-123",
        project_id="proj-alpha",
        pipeline_id="pipe-123",
        status="SUCCESS",
        stage="BRONZE_TO_SILVER",
        target_tier="SILVER",
        target_dataset="clean_metrics",
        records_processed=100,
        duration_ms=540,
        exit_code=0,
        logs="Done",
        effective_cpu_limit=3.0,
        effective_memory_limit="3g",
        requested_cpu_limit=3.0,
        requested_memory_limit="3g",
        resource_clamped=False,
        details={"cpu_source": "run_override", "memory_source": "run_override"},
        started_at=now,
        completed_at=now,
    )
    assert run_resp.effective_cpu_limit == 3.0
    assert run_resp.effective_memory_limit == "3g"
    assert run_resp.resource_clamped is False


def test_api_routes_resource_validation_and_contracts():
    app = FastAPI()
    app.include_router(pipeline_router)
    client = TestClient(app)
    now = datetime.now(timezone.utc)

    with patch("src.domains.pipeline.api.routes.facade") as mock_facade:
        # 1. Out-of-bounds CPU on pipeline create -> 400 Bad Request
        mock_facade.create_project_pipeline = AsyncMock(
            side_effect=ValueError("Requested CPU limit 8.0 cores exceeds administrator hard maximum cap of 4.0 cores.")
        )
        res_err = client.post(
            "/api/v1/projects/alpha/pipelines",
            json={
                "name": "heavy_pipe",
                "stage": "BRONZE_TO_SILVER",
                "script_content": "print('ok')",
                "default_cpu_limit": 8.0,
            },
        )
        assert res_err.status_code == 400
        assert "exceeds administrator hard maximum cap" in res_err.json()["detail"]

        # 2. Valid pipeline create with default resources -> 201 Created
        mock_facade.create_project_pipeline = AsyncMock(
            return_value=PipelineResponseContract(
                pipeline_id="pipe-1",
                project_id="alpha",
                name="bounded_pipe",
                stage="BRONZE_TO_SILVER",
                docker_image="artemis-pipeline-runner:latest",
                default_cpu_limit=1.5,
                default_memory_limit="1g",
                version=1,
                created_by="admin",
                created_at=now,
                updated_at=now,
            )
        )
        res_ok = client.post(
            "/api/v1/projects/alpha/pipelines",
            json={
                "name": "bounded_pipe",
                "stage": "BRONZE_TO_SILVER",
                "script_content": "print('ok')",
                "default_cpu_limit": 1.5,
                "default_memory_limit": "1g",
            },
        )
        assert res_ok.status_code == 201
        assert res_ok.json()["default_cpu_limit"] == 1.5
        assert res_ok.json()["default_memory_limit"] == "1g"

        # 3. Trigger run with out-of-bounds memory under reject policy -> 400 Bad Request
        mock_facade.trigger_pipeline_run = AsyncMock(
            side_effect=ValueError("Requested memory limit '8g' exceeds administrator hard maximum cap of '4g'.")
        )
        run_err = client.post(
            "/api/v1/projects/alpha/pipelines/pipe-1/run",
            json={
                "input_datasets": ["raw"],
                "target_dataset": "clean",
                "target_tier": "SILVER",
                "memory_limit": "8g",
            },
        )
        assert run_err.status_code == 400
        assert "exceeds administrator hard maximum cap" in run_err.json()["detail"]

        # 4. Trigger run with valid custom CPU/memory -> 200 OK with effective limits
        mock_facade.trigger_pipeline_run = AsyncMock(
            return_value=PipelineRunResponseContract(
                run_id="run-1",
                project_id="alpha",
                pipeline_id="pipe-1",
                status="SUCCESS",
                stage="BRONZE_TO_SILVER",
                target_tier="SILVER",
                target_dataset="clean",
                records_processed=42,
                duration_ms=800,
                exit_code=0,
                logs="Success",
                effective_cpu_limit=2.5,
                effective_memory_limit="2048m",
                requested_cpu_limit=2.5,
                requested_memory_limit="2048m",
                resource_clamped=False,
                details={"oom_killed": False},
                started_at=now,
                completed_at=now,
            )
        )
        run_ok = client.post(
            "/api/v1/projects/alpha/pipelines/pipe-1/run",
            json={
                "input_datasets": ["raw"],
                "target_dataset": "clean",
                "target_tier": "SILVER",
                "cpu_limit": 2.5,
                "memory_limit": "2048m",
            },
        )
        assert run_ok.status_code == 200
        body = run_ok.json()
        assert body["effective_cpu_limit"] == 2.5
        assert body["effective_memory_limit"] == "2048m"
        assert body["resource_clamped"] is False


def test_cli_pipeline_resource_flags_and_json_output(tmp_path):
    runner = CliRunner()
    script_file = tmp_path / "script.py"
    script_file.write_text("print('hello')\n", encoding="utf-8")
    now = datetime.now(timezone.utc)

    with patch("src.cli.commands.project.pipeline_facade") as mock_facade:
        # 1. CLI create with --default-cpu and --default-memory
        mock_facade.create_project_pipeline = AsyncMock(
            return_value=PipelineResponseContract(
                pipeline_id="pipe-cli-1",
                project_id="alpha",
                name="cli_pipe",
                stage="BRONZE_TO_SILVER",
                docker_image="artemis-pipeline-runner:latest",
                default_cpu_limit=1.5,
                default_memory_limit="1g",
                version=1,
                created_by="admin",
                created_at=now,
                updated_at=now,
            )
        )
        create_res = runner.invoke(
            project_group,
            [
                "pipeline",
                "create",
                "--project",
                "alpha",
                "--name",
                "cli_pipe",
                "--script",
                str(script_file),
                "--default-cpu",
                "1.5",
                "--default-memory",
                "1g",
                "--json",
            ],
        )
        assert create_res.exit_code == 0
        payload = json.loads(create_res.output)
        assert payload["default_cpu_limit"] == 1.5
        assert payload["default_memory_limit"] == "1g"

        # 2. CLI run with --cpu and --memory
        mock_facade.trigger_pipeline_run = AsyncMock(
            return_value=PipelineRunResponseContract(
                run_id="run-cli-1",
                project_id="alpha",
                pipeline_id="pipe-cli-1",
                status="SUCCESS",
                stage="BRONZE_TO_SILVER",
                target_tier="SILVER",
                target_dataset="clean_out",
                records_processed=10,
                duration_ms=320,
                exit_code=0,
                logs="Done",
                effective_cpu_limit=3.0,
                effective_memory_limit="3g",
                requested_cpu_limit=3.0,
                requested_memory_limit="3g",
                resource_clamped=False,
                started_at=now,
                completed_at=now,
            )
        )
        run_res = runner.invoke(
            project_group,
            [
                "pipeline",
                "run",
                "--project",
                "alpha",
                "--name",
                "cli_pipe",
                "--target-dataset",
                "clean_out",
                "--cpu",
                "3.0",
                "--memory",
                "3g",
            ],
        )
        assert run_res.exit_code == 0
        assert "Resources Applied: CPU=3.0 cores, Memory=3g" in run_res.output
