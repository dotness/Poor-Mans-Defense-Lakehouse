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
except ImportError:
    from config.settings import settings
    from domains.pipeline.models.contract.project_pipeline import (
        PipelineRunTriggerContract,
        PipelineRunResponseContract,
    )
    from domains.pipeline.operations.pipeline_manager import PipelineManager
    from domains.pipeline.operations.docker_runner import DockerPipelineRunner
    from domains.pipeline.operations.dataset_stager import DatasetStager

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
        """Executes a pipeline transformation script with dataset mapping."""
        # 1. Fetch Pipeline
        pipeline = self.pipeline_manager.get_pipeline(project_id, identifier)
        if not pipeline:
            raise ValueError(f"Pipeline '{identifier}' not found in project '{project_id}'.")

        script_content = self.pipeline_manager.get_pipeline_script(project_id, identifier)
        if not script_content:
            raise ValueError(f"Script content missing for pipeline '{identifier}'.")

        # 2. Record initial PENDING/RUNNING run record
        run_record = self.pipeline_manager.create_run_record(
            project_id=project_id,
            pipeline_id=pipeline.pipeline_id,
            stage=pipeline.stage,
            target_tier=contract.target_tier,
            target_dataset=contract.target_dataset,
            input_datasets=contract.input_datasets,
        )

        run_id = run_record.run_id
        workspace_dir = Path(settings.pipeline_workspace_dir) / run_id
        input_dir = workspace_dir / "input"
        output_dir = workspace_dir / "output"
        input_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            # 3. Stage inputs
            self.dataset_stager.stage_inputs(
                project_id=project_id,
                input_datasets=contract.input_datasets,
                staging_input_dir=input_dir,
                inline_data=contract.input_data,
            )

            # 4. Execute in ephemeral Docker sandbox
            runner_result = self.docker_runner.execute_script(
                script_content=script_content,
                input_dir=input_dir,
                output_dir=output_dir,
                image=pipeline.docker_image,
                timeout_seconds=contract.timeout_seconds,
                environment={"PROJECT_ID": project_id, "TARGET_DATASET": contract.target_dataset},
            )

            if runner_result.success:
                # 5. Commit output datasets to MinIO / Memgraph
                storage_uri, total_records, total_size = self.dataset_stager.commit_outputs(
                    project_id=project_id,
                    target_dataset=contract.target_dataset,
                    target_tier=contract.target_tier,
                    staging_output_dir=output_dir,
                )

                final_run = self.pipeline_manager.complete_run_record(
                    run_id=run_id,
                    status="SUCCESS",
                    records_processed=total_records,
                    duration_ms=runner_result.duration_ms,
                    exit_code=runner_result.exit_code,
                    logs=runner_result.logs,
                    details={
                        "storage_uri": storage_uri,
                        "size_bytes": total_size,
                        "container_id": runner_result.container_id,
                    },
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
                status_str = "TIMED_OUT" if runner_result.exit_code == 124 else "FAILED"
                final_run = self.pipeline_manager.complete_run_record(
                    run_id=run_id,
                    status=status_str,
                    records_processed=0,
                    duration_ms=runner_result.duration_ms,
                    exit_code=runner_result.exit_code,
                    logs=runner_result.logs,
                    details={"error": runner_result.error_message},
                )
                logger.warning(f"Pipeline run {run_id} {status_str}: {runner_result.error_message}")
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
                details={"error": str(e)},
            )
        finally:
            shutil.rmtree(workspace_dir, ignore_errors=True)
