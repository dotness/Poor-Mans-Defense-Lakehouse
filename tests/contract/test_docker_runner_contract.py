import pytest
from pathlib import Path
from src.domains.pipeline.operations.docker_runner import DockerPipelineRunner


def test_docker_runner_contract_mock_execution(mock_docker_runner, tmp_path):
    runner = mock_docker_runner

    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()

    script = """
import os
print("Runner contract test passed")
with open(os.path.join(os.getcwd(), "output", "result.txt"), "w") as f:
    f.write("OK")
"""

    res = runner.execute_script(
        script_content=script,
        input_dir=input_dir,
        output_dir=output_dir,
        timeout_seconds=10,
    )

    assert res.success is True
    assert res.exit_code == 0
    assert "Runner contract test passed" in res.logs
    assert res.duration_ms >= 0


def test_docker_runner_contract_failure_handling(mock_docker_runner, tmp_path):
    runner = mock_docker_runner

    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()

    script = "import sys; print('Simulated crash'); sys.exit(42)"

    res = runner.execute_script(
        script_content=script,
        input_dir=input_dir,
        output_dir=output_dir,
        timeout_seconds=10,
    )

    assert res.success is False
    assert res.exit_code == 42
    assert "Simulated crash" in res.logs
