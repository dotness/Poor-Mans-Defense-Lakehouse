import pytest
from datetime import datetime, timezone
from pydantic import ValidationError
from src.domains.pipeline.models.contract.project_pipeline import (
    PipelineCreateContract,
    PipelineUpdateContract,
    PipelineResponseContract,
    PipelineRunTriggerContract,
    PipelineRunResponseContract,
)
from src.domains.pipeline.operations.script_validator import validate_python_script


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
    )
    assert contract.name == "Cleanse Logs"
    assert contract.stage == "BRONZE_TO_SILVER"
    assert contract.docker_image == "artemis-pipeline-runner:latest"


def test_pipeline_run_trigger_contract():
    trigger = PipelineRunTriggerContract(
        input_datasets=["raw_metrics"],
        target_dataset="clean_metrics",
        target_tier="SILVER",
        timeout_seconds=120,
    )
    assert trigger.target_dataset == "clean_metrics"
    assert trigger.target_tier == "SILVER"
    assert trigger.timeout_seconds == 120
