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
        ttl_expression: Optional[str] = None,
        timestamp_column: Optional[str] = None,
        overwrite: bool = False,
    ) -> TabularIngestResponseContract:
        """Ingests tabular data to S3, registers it in the project dataset catalog, and records partition TTL state."""
        # Verify project exists
        project = self.project_manager.get_project(project_id)
        if not project:
            raise ValueError(f"Project '{project_id}' does not exist.")

        tier_norm = tier.upper()
        lease_id = None
        retention_repo = None
        try:
            from src.domains.retention.operations.retention_repository import RetentionRepository
            retention_repo = RetentionRepository()
            lease_id = retention_repo.acquire_lease(project_id, dataset_name, "INGESTION")
        except Exception:
            pass

        try:
            storage_uri, record_count, size_bytes = self.s3_storage.upload_tabular_data(
                project_id=project_id,
                dataset_name=dataset_name,
                tier=tier_norm,
                data_bytes=data_bytes,
                filename=filename,
                overwrite=overwrite,
                timestamp_column=timestamp_column,
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

            effective_ttl = ttl_expression
            try:
                from src.domains.retention.operations.policy_resolver import PolicyResolver
                obj_key = getattr(self.s3_storage, "last_uploaded_object_key", None) or storage_uri.replace(
                    f"s3://{getattr(self.s3_storage, 'bucket', 'telemetry')}/", ""
                )
                min_ts = getattr(self.s3_storage, "last_uploaded_min_event_ts", None)
                max_ts = getattr(self.s3_storage, "last_uploaded_max_event_ts", None)
                if retention_repo is not None:
                    retention_repo.add_partition(
                        project_id=project_id,
                        dataset_id=dataset_name,
                        tier=tier_norm,
                        object_key=obj_key,
                        storage_uri=storage_uri,
                        size_bytes=size_bytes,
                        record_count=record_count,
                        min_event_ts=min_ts,
                        max_event_ts=max_ts,
                        overwrite=overwrite,
                    )
                    resolver = PolicyResolver(repository=retention_repo)
                    if ttl_expression or timestamp_column:
                        from src.domains.retention.models.contract.retention import DatasetTTLSetRequestContract
                        pol, _ = resolver.resolve_effective_dataset_policy(project_id, dataset_name, tier_norm)
                        req = DatasetTTLSetRequestContract(
                            tier=tier_norm,
                            ttl_expression=ttl_expression or pol.ttl_expression,
                            granularity="TIMESTAMP_COLUMN" if timestamp_column else pol.granularity,
                            timestamp_column=timestamp_column or pol.timestamp_column,
                            grace_period_expression=pol.grace_period_expression,
                        )
                        st = resolver.set_dataset_ttl(project_id, dataset_name, req)
                    else:
                        st = resolver.compute_and_persist_dataset_state(
                            project_id=project_id,
                            dataset_id=dataset_name,
                            tier=tier_norm,
                            allow_implicit_restore=overwrite,
                        )
                    effective_ttl = st.effective_ttl_expression
            except Exception as re_err:
                logger.debug(f"Retention state registration notice: {re_err}")

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
                effective_ttl_expression=effective_ttl,
            )
        finally:
            if lease_id and retention_repo is not None:
                try:
                    retention_repo.release_lease(lease_id)
                except Exception:
                    pass

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
        dataset_name: str = "knowledge_graph",
        ttl_expression: Optional[str] = None,
        overwrite: bool = False,
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
        storage_uri = f"memgraph://tagged/{project_id}/{dataset_name}"
        self.project_manager.record_dataset(
            project_id=project_id,
            dataset_id=dataset_name,
            tier="BRONZE",
            dataset_type="GRAPH",
            storage_uri=storage_uri,
            size_bytes=0,
            record_count=nodes_imported + edges_imported,
        )

        try:
            from src.domains.retention.operations.retention_repository import RetentionRepository
            from src.domains.retention.operations.policy_resolver import PolicyResolver
            from src.domains.retention.models.contract.retention import DatasetTTLSetRequestContract
            repo = RetentionRepository()
            repo.add_partition(
                project_id=project_id,
                dataset_id=dataset_name,
                tier="BRONZE",
                object_key="",
                storage_uri=storage_uri,
                size_bytes=0,
                record_count=nodes_imported + edges_imported,
                overwrite=overwrite,
            )
            resolver = PolicyResolver(repository=repo)
            if ttl_expression:
                resolver.set_dataset_ttl(
                    project_id,
                    dataset_name,
                    DatasetTTLSetRequestContract(tier="BRONZE", ttl_expression=ttl_expression),
                )
            else:
                resolver.compute_and_persist_dataset_state(project_id, dataset_name, "BRONZE", allow_implicit_restore=overwrite)
        except Exception as e:
            logger.debug(f"Graph retention state notice: {e}")

        return GraphIngestResponseContract(
            status="SUCCESS",
            project_id=project_id,
            nodes_imported=nodes_imported,
            edges_imported=edges_imported,
        )
