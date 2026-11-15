import os
import time
import uuid
import shutil
import logging
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, Optional, Any
import docker
from docker.errors import DockerException, ContainerError

try:
    from src.config.settings import settings
except ImportError:
    from config.settings import settings

from src.core.exceptions import ConnectionError, ServiceUnavailableError

logger = logging.getLogger("artemis.pipeline.docker")


@dataclass
class DockerRunnerResult:
    exit_code: int
    logs: str
    duration_ms: int
    container_id: Optional[str] = None
    success: bool = True
    error_message: Optional[str] = None


class DockerPipelineRunner:
    """Manages ephemeral Docker container execution for user-uploaded pipeline transformation scripts."""

    def __init__(
        self,
        default_image: Optional[str] = None,
        workspace_base: Optional[Path] = None,
        client: Optional[docker.DockerClient] = None,
        docker_url: Optional[str] = None,
    ):
        self.default_image = default_image or settings.docker_runner_image
        self.workspace_base = Path(workspace_base or settings.pipeline_workspace_dir)
        self.workspace_base.mkdir(parents=True, exist_ok=True)

        if client is not None:
            self._client: Optional[docker.DockerClient] = client
        else:
            try:
                if docker_url:
                    self._client = docker.DockerClient(base_url=docker_url)
                else:
                    self._client = docker.from_env()
                self._client.ping()
            except Exception as e:
                logger.error(f"Docker engine not accessible ({e})")
                raise ConnectionError(
                    f"Docker engine is not accessible: {e}",
                    original_cause=e,
                ) from e

    def execute_script(
        self,
        script_content: str,
        input_dir: Path,
        output_dir: Path,
        image: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        environment: Optional[Dict[str, str]] = None,
    ) -> DockerRunnerResult:
        """
        Executes a script inside an ephemeral Docker container.
        Input files are mounted at /workspace/input (read-only).
        Output files must be written to /workspace/output (read-write).
        """
        image_tag = image or self.default_image
        timeout = timeout_seconds or settings.docker_run_timeout
        run_id = f"run_{uuid.uuid4().hex[:12]}"
        run_workspace = self.workspace_base / run_id
        run_workspace.mkdir(parents=True, exist_ok=True)

        script_file = run_workspace / "main.py"
        script_file.write_text(script_content, encoding="utf-8")

        start_time = time.monotonic()
        container = None

        try:
            # Real Docker execution
            volumes = {
                str(input_dir.resolve()): {"bind": "/workspace/input", "mode": "ro"},
                str(output_dir.resolve()): {"bind": "/workspace/output", "mode": "rw"},
                str(script_file.resolve()): {"bind": "/workspace/main.py", "mode": "ro"},
            }

            container_env = environment or {}

            container = self._client.containers.run(
                image=image_tag,
                command=["python", "/workspace/main.py"],
                volumes=volumes,
                environment=container_env,
                working_dir="/workspace",
                network_mode="none",
                mem_limit=settings.docker_runner_memory_limit,
                nano_cpus=int(settings.docker_runner_cpu_limit * 1e9),
                detach=True,
                remove=False,
                name=f"artemis-runner-{run_id}",
            )

            # Wait for container completion with timeout
            result = container.wait(timeout=timeout)
            duration_ms = int((time.monotonic() - start_time) * 1000)

            exit_code = result.get("StatusCode", 1)
            logs = container.logs(stdout=True, stderr=True).decode("utf-8", errors="replace")

            success = (exit_code == 0)
            return DockerRunnerResult(
                exit_code=exit_code,
                logs=logs,
                duration_ms=duration_ms,
                container_id=container.id,
                success=success,
                error_message=None if success else f"Script exited with status {exit_code}",
            )

        except docker.errors.ContainerError as e:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            logs = e.stderr.decode("utf-8", errors="replace") if hasattr(e, "stderr") and e.stderr else str(e)
            return DockerRunnerResult(
                exit_code=e.exit_status,
                logs=logs,
                duration_ms=duration_ms,
                container_id=e.container.id if hasattr(e, "container") else None,
                success=False,
                error_message=f"Container execution failed: {e}",
            )

        except Exception as e:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            # Timeout or Docker daemon error
            is_timeout = "timeout" in str(e).lower()
            return DockerRunnerResult(
                exit_code=-1 if is_timeout else 1,
                logs=f"Container execution error: {e}",
                duration_ms=duration_ms,
                container_id=container.id if container else None,
                success=False,
                error_message=f"Timeout after {timeout}s" if is_timeout else str(e),
            )

        finally:
            if container:
                try:
                    container.remove(force=True)
                except Exception as ce:
                    logger.warning(f"Failed to remove container {container.id}: {ce}")
            if run_workspace.exists():
                try:
                    shutil.rmtree(run_workspace)
                except Exception as we:
                    logger.warning(f"Failed to cleanup run workspace {run_workspace}: {we}")
