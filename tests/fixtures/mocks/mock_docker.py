import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Dict, Optional

from src.domains.pipeline.operations.docker_runner import DockerRunnerResult


class MockDockerRunner:
    """In-memory / local subprocess test double for DockerPipelineRunner."""

    def __init__(
        self,
        default_image: Optional[str] = "python:3.12-slim",
        workspace_base: Optional[Path] = None,
    ):
        self.default_image = default_image
        self.workspace_base = Path(workspace_base or "/tmp/artemis/mock_pipeline_workspace")
        self.workspace_base.mkdir(parents=True, exist_ok=True)

    def execute_script(
        self,
        script_content: str,
        input_dir: Path,
        output_dir: Path,
        image: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        environment: Optional[Dict[str, str]] = None,
    ) -> DockerRunnerResult:
        run_id = uuid.uuid4().hex[:8]
        run_workspace = self.workspace_base / run_id
        run_workspace.mkdir(parents=True, exist_ok=True)

        script_file = run_workspace / "transform.py"
        with open(script_file, "w") as f:
            f.write(script_content)

        timeout = timeout_seconds or 30
        start_time = time.monotonic()

        try:
            (run_workspace / "input").symlink_to(input_dir.resolve(), target_is_directory=True)
            (run_workspace / "output").symlink_to(output_dir.resolve(), target_is_directory=True)

            env = os.environ.copy()
            if environment:
                env.update(environment)

            res = subprocess.run(
                [os.sys.executable, str(script_file)],
                cwd=str(run_workspace),
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            duration_ms = int((time.monotonic() - start_time) * 1000)
            logs = f"{res.stdout}\n{res.stderr}".strip()
            success = res.returncode == 0
            return DockerRunnerResult(
                exit_code=res.returncode,
                logs=logs,
                duration_ms=duration_ms,
                container_id=f"mock-{run_id}",
                success=success,
                error_message=None if success else f"Script exited with status {res.returncode}",
            )
        except subprocess.TimeoutExpired:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            return DockerRunnerResult(
                exit_code=-1,
                logs=f"Mock execution timed out after {timeout} seconds",
                duration_ms=duration_ms,
                container_id=f"mock-{run_id}",
                success=False,
                error_message=f"Container execution timed out after {timeout}s",
            )
        except Exception as e:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            return DockerRunnerResult(
                exit_code=1,
                logs=str(e),
                duration_ms=duration_ms,
                container_id=f"mock-{run_id}",
                success=False,
                error_message=str(e),
            )
