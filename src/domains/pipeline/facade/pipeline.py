import logging
from typing import List, Optional, Dict, Any
from src.base.facade import DomainFacade
from src.domains.pipeline.models.contract.pipeline import PipelineRunRequestContract, PipelineRunResponseContract as LegacyPipelineRunResponseContract
from src.domains.pipeline.models.contract.project_pipeline import (
    PipelineCreateContract,
    PipelineUpdateContract,
    PipelineResponseContract,
    PipelineRunTriggerContract,
    PipelineRunResponseContract,
)
from src.domains.pipeline.operations.pipeline_manager import PipelineManager
from src.domains.ingestion.facade.ingestion import IngestionFacade

logger = logging.getLogger(__name__)


class PipelineFacade(DomainFacade):
    """Facade for pipeline management and batch workflow execution."""

    def __init__(self, pipeline_manager: Optional[PipelineManager] = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ingestion_facade = IngestionFacade()
        self.pipeline_manager = pipeline_manager or PipelineManager()
        self._executor = None

    @property
    def executor(self):
        if self._executor is None:
            from src.domains.pipeline.operations.pipeline_executor import PipelineExecutor
            self._executor = PipelineExecutor(pipeline_manager=self.pipeline_manager)
        return self._executor

    async def run_pipeline(self, request: PipelineRunRequestContract) -> LegacyPipelineRunResponseContract:
        """Executes a legacy named batch pipeline (e.g. mqtt_to_minio)."""
        name = request.pipeline_name
        if name == "mqtt_to_minio":
            res = await self.ingestion_facade.flush_buffer_to_minio()
            return LegacyPipelineRunResponseContract(
                status=res.status,
                pipeline_name=name,
                events_processed=res.events_processed,
                object_key=res.object_key,
                details=res.details,
            )
        else:
            raise ValueError(f"Unknown pipeline '{name}'. Available: ['mqtt_to_minio']")

    # --- Project Pipeline CRUD Operations ---

    async def create_project_pipeline(
        self,
        project_id: str,
        contract: PipelineCreateContract,
        created_by: str = "admin",
    ) -> PipelineResponseContract:
        return self.pipeline_manager.create_pipeline(project_id, contract, created_by)

    async def get_project_pipeline(
        self,
        project_id: str,
        identifier: str,
    ) -> Optional[PipelineResponseContract]:
        return self.pipeline_manager.get_pipeline(project_id, identifier)

    async def list_project_pipelines(
        self,
        project_id: str,
    ) -> List[PipelineResponseContract]:
        return self.pipeline_manager.list_pipelines(project_id)

    async def update_project_pipeline(
        self,
        project_id: str,
        identifier: str,
        contract: PipelineUpdateContract,
    ) -> PipelineResponseContract:
        return self.pipeline_manager.update_pipeline(project_id, identifier, contract)

    async def delete_project_pipeline(
        self,
        project_id: str,
        identifier: str,
    ) -> bool:
        return self.pipeline_manager.delete_pipeline(project_id, identifier)

    async def list_pipeline_runs(
        self,
        project_id: str,
        pipeline_id: Optional[str] = None,
    ) -> List[PipelineRunResponseContract]:
        return self.pipeline_manager.list_runs(project_id, pipeline_id)

    async def trigger_pipeline_run(
        self,
        project_id: str,
        identifier: str,
        contract: PipelineRunTriggerContract,
    ) -> PipelineRunResponseContract:
        return self.executor.trigger_run(project_id, identifier, contract)
