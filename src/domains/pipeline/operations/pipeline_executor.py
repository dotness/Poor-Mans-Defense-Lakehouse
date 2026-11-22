import logging
import uuid
import shutil
from pathlib import Path
from typing import Optional, Dict, Any

try:
    from src.config.settings import settings
    from src.domains.pipeline.models.contract.project_pipeline import (
        PipelineRunTriggerContract,
        PipelineRunResponseContract,
    )
    from src.domains.pipeline.operations.pipeline_manager import PipelineManager
    from src.domains.pipeline.operations.docker_runner import DockerPipelineRunner
    from src.domains.pipeline.operations.dataset_stager import DatasetStager
    from src.domains.pipeline.operations.resource_validator import resolve_run_resources
except ImportError:
    from config.settings import settings
    from domains.pipeline.models.contract.project_pipeline import (
        PipelineRunTriggerContract,
        PipelineRunResponseContract,
    )
    from domains.pipeline.operations.pipeline_manager import PipelineManager
    from domains.pipeline.operations.docker_runner import DockerPipelineRunner
    from domains.pipeline.operations.dataset_stager import DatasetStager
    from domains.pipeline.operations.resource_validator import resolve_run_resources

logger = logging.getLogger("artemis.pipeline.executor")


class PipelineExecutor:
    """Orchestrates end-to-end execution of a pipeline inside an ephemeral Docker sandbox."""

    def __init__(
        self,
        pipeline_manager: Optional[PipelineManager] = None,
        docker_runner: Optional[DockerPipelineRunner] = None,
        dataset_stager: Optional[DatasetStager] = None,
    ):
        self.pipeline_manager = pipeline_manager or PipelineManager()
        self.docker_runner = docker_runner or DockerPipelineRunner()
        self.dataset_stager = dataset_stager or DatasetStager()

    def trigger_run(
        self,
        project_id: str,
        identifier: str,
        contract: PipelineRunTriggerContract,
    ) -> PipelineRunResponseContract:
        """Executes a pipeline transformation script with dataset mapping and resource limit enforcement."""
        # 1. Fetch Pipeline
        pipeline = self.pipeline_manager.get_pipeline(project_id, identifier)
        if not pipeline:
            raise ValueError(f"Pipeline '{identifier}' not found in project '{project_id}'.")

        script_content = self.pipeline_manager.get_pipeline_script(project_id, identifier)
        if not script_content:
            raise ValueError(f"Script content missing for pipeline '{identifier}'.")

        # 2. Resolve and validate CPU/memory allocations BEFORE creating run record or container (FR-004..FR-008)
        resolved_resources = resolve_run_resources(
            requested_cpu_limit=contract.cpu_limit,
            requested_memory_limit=contract.memory_limit,
            pipeline_default_cpu_limit=getattr(pipeline, "default_cpu_limit", None),
            pipeline_default_memory_limit=getattr(pipeline, "default_memory_limit", None),
        )
        resource_meta = resolved_resources.to_metadata_dict()

        # 3. Record initial RUNNING run record with resolved resource allocation metadata
        run_record = self.pipeline_manager.create_run_record(
            project_id=project_id,
            pipeline_id=pipeline.pipeline_id,
            stage=pipeline.stage,
            target_tier=contract.target_tier,
            target_dataset=contract.target_dataset,
            input_datasets=contract.input_datasets,
            details=dict(resource_meta),
        )

        run_id = run_record.run_id
        workspace_dir = Path(settings.pipeline_workspace_dir) / run_id
        input_dir = workspace_dir / "input"
        output_dir = workspace_dir / "output"
        input_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Acquire active operation leases for input and target datasets (FR-011)
        acquired_leases = []
        retention_repo = None
        try:
            from src.domains.retention.operations.retention_repository import RetentionRepository
            retention_repo = RetentionRepository()
            datasets_to_lock = set(contract.input_datasets or [])
            if contract.target_dataset:
                datasets_to_lock.add(contract.target_dataset)
            for ds_name in datasets_to_lock:
                lid = retention_repo.acquire_lease(
                    project_id=project_id,
                    dataset_id=ds_name,
                    operation_type="PIPELINE_RUN",
                    holder_id=run_id,
                    ttl_seconds=max(300, int(contract.timeout_seconds or 300) + 60),
                )
                acquired_leases.append(lid)
        except Exception as lease_err:
            logger.debug(f"Pipeline lease acquisition notice: {lease_err}")

        try:
            # 4. Stage inputs
            self.dataset_stager.stage_inputs(
                project_id=project_id,
                input_datasets=contract.input_datasets,
                staging_input_dir=input_dir,
                inline_data=contract.input_data,
            )

            # 5. Execute in ephemeral Docker sandbox with resolved effective CPU and memory limits (FR-009)
            runner_result = self.docker_runner.execute_script(
                script_content=script_content,
                input_dir=input_dir,
                output_dir=output_dir,
                image=pipeline.docker_image,
                timeout_seconds=contract.timeout_seconds,
                environment={"PROJECT_ID": project_id, "TARGET_DATASET": contract.target_dataset},
                cpu_limit=resolved_resources.effective_cpu_limit,
                memory_limit=resolved_resources.effective_memory_limit,
            )

            if runner_result.success:
                # 6. Commit output datasets to MinIO / Memgraph
                storage_uri, total_records, total_size = self.dataset_stager.commit_outputs(
                    project_id=project_id,
                    target_dataset=contract.target_dataset,
                    target_tier=contract.target_tier,
                    staging_output_dir=output_dir,
                )

                completion_details = {
                    **resource_meta,
                    "storage_uri": storage_uri,
                    "size_bytes": total_size,
                    "container_id": runner_result.container_id,
                    "oom_killed": False,
                }
                final_run = self.pipeline_manager.complete_run_record(
                    run_id=run_id,
                    status="SUCCESS",
                    records_processed=total_records,
                    duration_ms=runner_result.duration_ms,
                    exit_code=runner_result.exit_code,
                    logs=runner_result.logs,
                    details=completion_details,
                )
                # Record lineage in KDG graph store (failure-safe)
                try:
                    from src.domains.discovery.operations.kdg_graph_store import KDGGraphStore
                    kdg_store = KDGGraphStore()
                    kdg_store.record_pipeline_execution(
                        run_id=run_id,
                        pipeline_id=pipeline.pipeline_id,
                        project_id=project_id,
                        status="SUCCESS",
                        input_datasets=contract.input_datasets,
                        target_dataset=contract.target_dataset,
                    )
                except Exception as kdg_err:
                    logger.warning(f"KDG lineage recording encountered error (pipeline execution unaffected): {kdg_err}")

                logger.info(f"Pipeline run {run_id} succeeded in {runner_result.duration_ms}ms")
                return final_run

            else:
                is_oom = bool(getattr(runner_result, "oom_killed", False)) or runner_result.exit_code == 137
                status_str = "TIMED_OUT" if runner_result.exit_code == 124 else "FAILED"
                if is_oom:
                    oom_msg = (
                        f"Out of Memory (OOM): Container killed (exit code 137) "
                        f"after exceeding effective memory limit of {resolved_resources.effective_memory_limit}."
                    )
                    error_msg = oom_msg
                    logs_str = runner_result.logs or ""
                    if oom_msg not in logs_str:
                        logs_str = f"{logs_str.rstrip()}\n{oom_msg}".strip() if logs_str else oom_msg
                    exit_code_val = 137
                else:
                    error_msg = runner_result.error_message
                    logs_str = runner_result.logs
                    exit_code_val = runner_result.exit_code

                failure_details = {
                    **resource_meta,
                    "error": error_msg,
                    "container_id": runner_result.container_id,
                    "oom_killed": is_oom,
                }
                final_run = self.pipeline_manager.complete_run_record(
                    run_id=run_id,
                    status=status_str,
                    records_processed=0,
                    duration_ms=runner_result.duration_ms,
                    exit_code=exit_code_val,
                    logs=logs_str,
                    details=failure_details,
                )
                logger.warning(f"Pipeline run {run_id} {status_str}: {error_msg}")
                return final_run

        except Exception as e:
            logger.error(f"Unexpected error executing pipeline run {run_id}: {e}")
            return self.pipeline_manager.complete_run_record(
                run_id=run_id,
                status="FAILED",
                records_processed=0,
                duration_ms=0,
                exit_code=1,
                logs=str(e),
                details={**resource_meta, "error": str(e), "oom_killed": False},
            )
        finally:
            if acquired_leases and retention_repo is not None:
                for lid in acquired_leases:
                    try:
                        retention_repo.release_lease(lid)
                    except Exception:
                        pass
            shutil.rmtree(workspace_dir, ignore_errors=True)
