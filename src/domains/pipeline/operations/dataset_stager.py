import io
import json
import logging
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional

try:
    from src.domains.project.operations.s3_storage import ProjectS3Storage
    from src.domains.project.operations.project_manager import ProjectManager
    from src.domains.project.operations.graph_storage import ProjectGraphStorage
except ImportError:
    from domains.project.operations.s3_storage import ProjectS3Storage
    from domains.project.operations.project_manager import ProjectManager
    from domains.project.operations.graph_storage import ProjectGraphStorage

logger = logging.getLogger("artemis.pipeline.stager")


class DatasetStager:
    """Manages input staging from MinIO into local container mount directories and output commit to target tiers."""

    def __init__(
        self,
        s3_storage: Optional[ProjectS3Storage] = None,
        project_manager: Optional[ProjectManager] = None,
        graph_storage: Optional[ProjectGraphStorage] = None,
    ):
        self.s3 = s3_storage or ProjectS3Storage()
        self.project_manager = project_manager or ProjectManager()
        self.graph_storage = graph_storage or ProjectGraphStorage()

    def stage_inputs(
        self,
        project_id: str,
        input_datasets: List[str],
        staging_input_dir: Path,
        inline_data: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Downloads all input datasets from S3 into staging_input_dir.
        If inline_data is provided, writes it as raw_inline_payload.json.
        Returns total number of staged files.
        """
        staging_input_dir.mkdir(parents=True, exist_ok=True)
        staged_files_count = 0

        # 1. Download registered datasets from MinIO
        for ds in input_datasets:
            files = self.s3.download_dataset_files(
                project_id=project_id,
                dataset_name=ds,
                dest_dir=staging_input_dir,
            )
            staged_files_count += len(files)

        # 2. Write inline data if provided
        if inline_data:
            inline_file = staging_input_dir / "raw_inline_payload.json"
            inline_file.write_text(json.dumps(inline_data, indent=2), encoding="utf-8")
            staged_files_count += 1

        return staged_files_count

    def commit_outputs(
        self,
        project_id: str,
        target_dataset: str,
        target_tier: str,
        staging_output_dir: Path,
    ) -> Tuple[str, int, int]:
        """
        Collects all output files from staging_output_dir, uploads to target tier in MinIO,
        processes any graph extractions, and registers the target dataset in the catalog.
        Returns: (storage_uri, total_records, total_size_bytes)
        """
        staging_output_dir.mkdir(parents=True, exist_ok=True)
        tier_upper = target_tier.upper()

        # Check for graph output files (e.g. graph.json)
        graph_files = list(staging_output_dir.glob("*.json"))
        for gf in graph_files:
            try:
                data = json.loads(gf.read_text(encoding="utf-8"))
                if isinstance(data, dict) and ("nodes" in data or "edges" in data):
                    nodes = data.get("nodes", [])
                    edges = data.get("edges", [])
                    self.graph_storage.ingest_graph_data(project_id, nodes, edges)
                    logger.info(f"Ingested {len(nodes)} graph nodes and {len(edges)} edges from {gf.name}")
            except Exception as e:
                logger.debug(f"File {gf.name} not a graph payload: {e}")

        # Upload tabular output files to MinIO target partition
        storage_uri, total_records, total_size = self.s3.upload_output_directory(
            project_id=project_id,
            target_dataset=target_dataset,
            target_tier=tier_upper,
            source_dir=staging_output_dir,
        )

        # Catalog dataset in PostgreSQL
        self.project_manager.record_dataset(
            project_id=project_id,
            dataset_id=target_dataset,
            tier=tier_upper,
            dataset_type="PARQUET",
            storage_uri=storage_uri,
            size_bytes=total_size,
            record_count=total_records,
        )

        return storage_uri, total_records, total_size
