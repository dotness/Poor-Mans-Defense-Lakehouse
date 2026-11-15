import logging
from typing import Dict, Any, List, Optional
from src.domains.project.operations.s3_storage import ProjectS3Storage
from src.domains.project.operations.graph_storage import ProjectGraphStorage
from src.domains.project.operations.project_manager import ProjectManager
from src.domains.project.models.contract.project import (
    TabularIngestResponseContract,
    GraphIngestResponseContract,
)

logger = logging.getLogger("artemis.project.ingestion")


class ScopedIngestionService:
    """Coordinates tabular and graph ingestion scoped to a project."""

    def __init__(
        self,
        project_manager: Optional[ProjectManager] = None,
        s3_storage: Optional[ProjectS3Storage] = None,
        graph_storage: Optional[ProjectGraphStorage] = None,
    ):
        self.project_manager = project_manager or ProjectManager()
        self.s3_storage = s3_storage or ProjectS3Storage()
        self.graph_storage = graph_storage or ProjectGraphStorage()

    def ingest_tabular(
        self,
        project_id: str,
        dataset_name: str,
        data_bytes: bytes,
        filename: str,
        tier: str = "BRONZE",
    ) -> TabularIngestResponseContract:
        """Ingests tabular data to S3 and registers it in the project dataset catalog."""
        # Verify project exists
        project = self.project_manager.get_project(project_id)
        if not project:
            raise ValueError(f"Project '{project_id}' does not exist.")

        tier_norm = tier.upper()
        storage_uri, record_count, size_bytes = self.s3_storage.upload_tabular_data(
            project_id=project_id,
            dataset_name=dataset_name,
            tier=tier_norm,
            data_bytes=data_bytes,
            filename=filename,
        )

        ext = filename.lower().split(".")[-1] if "." in filename else "PARQUET"
        dataset_type = ext.upper()

        self.project_manager.record_dataset(
            project_id=project_id,
            dataset_id=dataset_name,
            tier=tier_norm,
            dataset_type=dataset_type,
            storage_uri=storage_uri,
            size_bytes=size_bytes,
            record_count=record_count,
        )

        # Knowledge Discovery Graph indexing hook (Failure-safe, never fails ingestion)
        try:
            self._trigger_kdg_indexing(
                project_id=project_id,
                dataset_name=dataset_name,
                data_bytes=data_bytes,
                filename=filename,
                dataset_type=dataset_type,
                tier=tier_norm,
                storage_uri=storage_uri,
            )
        except Exception as e:
            logger.warning(f"KDG indexing hook error (ingestion unaffected): {e}")

        return TabularIngestResponseContract(
            status="SUCCESS",
            project_id=project_id,
            tier=tier_norm,
            dataset_name=dataset_name,
            records_ingested=record_count,
            storage_uri=storage_uri,
        )

    def _trigger_kdg_indexing(
        self,
        project_id: str,
        dataset_name: str,
        data_bytes: bytes,
        filename: str,
        dataset_type: str,
        tier: str,
        storage_uri: str,
    ) -> None:
        import os
        import tempfile
        import asyncio

        try:
            from src.domains.discovery.operations.job_repository import IndexJobRepository
            from src.domains.discovery.operations.structural_indexer import StructuralIndexer
            from src.domains.discovery.operations.enrichment_workflow import dispatch_enrichment_job
        except ImportError:
            from domains.discovery.operations.job_repository import IndexJobRepository
            from domains.discovery.operations.structural_indexer import StructuralIndexer
            from domains.discovery.operations.enrichment_workflow import dispatch_enrichment_job

        job_repo = IndexJobRepository()
        job = job_repo.create_job(project_id=project_id, resource_id=dataset_name, phase="structural")

        tmp_path = ""
        try:
            suffix = f"_{filename}" if filename else ".dat"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(data_bytes)
                tmp_path = tmp.name

            indexer = StructuralIndexer()
            idx_res = indexer.index_resource(
                project_id=project_id,
                resource_id=dataset_name,
                file_path=tmp_path,
                format=dataset_type,
                tier=tier,
                location_uri=storage_uri,
            )

            if idx_res.get("status") == "SUCCESS":
                job_repo.transition_status(job.job_id, status="completed", phase="phase1_structural")
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(dispatch_enrichment_job(job.job_id, project_id, dataset_name, []))
                except RuntimeError:
                    pass
            else:
                job_repo.record_failure(job.job_id, error_message=idx_res.get("error", "Indexing error"))
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    def ingest_graph(
        self,
        project_id: str,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
    ) -> GraphIngestResponseContract:
        """Ingests graph entities into Memgraph tagged with project_id."""
        project = self.project_manager.get_project(project_id)
        if not project:
            raise ValueError(f"Project '{project_id}' does not exist.")

        nodes_imported, edges_imported = self.graph_storage.ingest_graph_data(
            project_id=project_id,
            nodes=nodes,
            edges=edges,
        )

        # Register dataset entry for graph
        self.project_manager.record_dataset(
            project_id=project_id,
            dataset_id="knowledge_graph",
            tier="BRONZE",
            dataset_type="GRAPH",
            storage_uri=f"memgraph://tagged/{project_id}",
            size_bytes=0,
            record_count=nodes_imported + edges_imported,
        )

        return GraphIngestResponseContract(
            status="SUCCESS",
            project_id=project_id,
            nodes_imported=nodes_imported,
            edges_imported=edges_imported,
        )
