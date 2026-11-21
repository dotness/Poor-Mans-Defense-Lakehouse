import io
import os
import uuid
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any
import pyarrow as pa
import pyarrow.csv as pcsv
import pyarrow.json as pjson
import pyarrow.parquet as pq
from minio import Minio

try:
    from src.config.settings import settings
except ImportError:
    from config.settings import settings

logger = logging.getLogger("artemis.project.s3")


class ProjectS3Storage:
    """Manages project-scoped S3 partitioning and dataset file transfer in MinIO."""

    def __init__(
        self,
        endpoint: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        bucket: Optional[str] = None,
        secure: Optional[bool] = None,
    ):
        self.endpoint = endpoint or settings.minio_endpoint
        self.access_key = access_key or settings.minio_access_key
        self.secret_key = secret_key or settings.minio_secret_key
        self.bucket = bucket or settings.minio_bucket
        self.secure = secure if secure is not None else settings.minio_use_ssl

        self.client = Minio(
            self.endpoint,
            access_key=self.access_key,
            secret_key=self.secret_key,
            secure=self.secure,
        )
        self.ensure_bucket()

    def ensure_bucket(self):
        try:
            if not self.client.bucket_exists(self.bucket):
                self.client.make_bucket(self.bucket)
                logger.info(f"Created MinIO bucket '{self.bucket}'")
        except Exception as e:
            logger.warning(f"Could not ensure bucket '{self.bucket}': {e}")

    def get_tier_prefix(self, project_id: str, tier: str, dataset_name: str) -> str:
        """Returns standard prefix: projects/{project_id}/{tier.lower()}/{dataset_name}/"""
        return f"projects/{project_id.strip()}/{tier.strip().lower()}/{dataset_name.strip()}/"

    def upload_tabular_data(
        self,
        project_id: str,
        dataset_name: str,
        tier: str,
        data_bytes: bytes,
        filename: str,
        overwrite: bool = False,
        timestamp_column: Optional[str] = None,
    ) -> Tuple[str, int, int]:
        """
        Uploads tabular data (CSV, JSON, Parquet) into the project's tier partition.
        Converts CSV / JSON into Parquet if possible for uniform lake querying, or stores natively.
        If overwrite=True, removes existing S3 objects under this dataset prefix first.
        Returns: (storage_uri, record_count, size_bytes)
        """
        now = datetime.now(timezone.utc)
        prefix = self.get_tier_prefix(project_id, tier, dataset_name)
        if overwrite:
            try:
                old_keys = self.list_dataset_objects(project_id, tier, dataset_name)
                for ok in old_keys:
                    self.client.remove_object(self.bucket, ok)
            except Exception as e:
                logger.debug(f"Could not remove previous objects on overwrite: {e}")

        date_partition = f"year={now.year:04d}/month={now.month:02d}/day={now.day:02d}"

        # Attempt to parse into PyArrow Table
        ext = filename.lower().split(".")[-1] if "." in filename else ""
        table = None
        record_count = 0
        self.last_uploaded_min_event_ts: Optional[datetime] = None
        self.last_uploaded_max_event_ts: Optional[datetime] = None
        self.last_uploaded_object_key: Optional[str] = None

        try:
            if ext == "parquet":
                table = pq.read_table(io.BytesIO(data_bytes))
            elif ext in ("csv", "tsv"):
                table = pcsv.read_csv(io.BytesIO(data_bytes))
            elif ext in ("json", "jsonl"):
                table = pjson.read_json(io.BytesIO(data_bytes))
        except Exception as e:
            logger.warning(f"Could not parse tabular file with pyarrow ({e}); falling back to raw upload")

        if table is not None:
            record_count = table.num_rows
            if timestamp_column:
                try:
                    from src.domains.retention.operations.parquet_compactor import extract_parquet_timestamp_bounds
                    min_ts, max_ts = extract_parquet_timestamp_bounds(table, timestamp_column)
                    self.last_uploaded_min_event_ts = min_ts
                    self.last_uploaded_max_event_ts = max_ts
                except Exception as te:
                    logger.debug(f"Timestamp extraction notice: {te}")
            sink = io.BytesIO()
            pq.write_table(table, sink, compression="SNAPPY")
            sink.seek(0)
            upload_bytes = sink.getvalue()
            object_name = f"{prefix}{date_partition}/batch_{int(now.timestamp())}_{uuid.uuid4().hex[:8]}.parquet"
        else:
            upload_bytes = data_bytes
            object_name = f"{prefix}{date_partition}/raw_{int(now.timestamp())}_{uuid.uuid4().hex[:8]}_{filename}"
            # Approximate record count by line count
            record_count = max(1, data_bytes.count(b"\n"))

        self.last_uploaded_object_key = object_name

        size_bytes = len(upload_bytes)
        self.client.put_object(
            bucket_name=self.bucket,
            object_name=object_name,
            data=io.BytesIO(upload_bytes),
            length=size_bytes,
            content_type="application/octet-stream",
        )

        storage_uri = f"s3://{self.bucket}/{object_name}"
        logger.info(f"Uploaded {record_count} records to {storage_uri}")
        return storage_uri, record_count, size_bytes

    def list_dataset_objects(self, project_id: str, tier: str, dataset_name: str) -> List[str]:
        """Lists object keys belonging to a specific project dataset."""
        prefix = self.get_tier_prefix(project_id, tier, dataset_name)
        objects = self.client.list_objects(self.bucket, prefix=prefix, recursive=True)
        return [obj.object_name for obj in objects]

    def download_dataset_files(
        self,
        project_id: str,
        dataset_name: str,
        dest_dir: Path,
        tier: Optional[str] = None,
    ) -> List[Path]:
        """
        Downloads all objects for a dataset into a local folder (e.g. for mounting into Docker /workspace/input).
        If tier is None, searches bronze, then silver, then gold.
        """
        dest_dir.mkdir(parents=True, exist_ok=True)
        tiers_to_search = [tier.lower()] if tier else ["bronze", "silver", "gold"]

        downloaded_paths = []
        for t in tiers_to_search:
            keys = self.list_dataset_objects(project_id, t, dataset_name)
            for k in keys:
                filename = Path(k).name
                local_path = dest_dir / f"{dataset_name}_{filename}"
                self.client.fget_object(self.bucket, k, str(local_path))
                downloaded_paths.append(local_path)

        return downloaded_paths

    def upload_output_directory(
        self,
        project_id: str,
        target_dataset: str,
        target_tier: str,
        source_dir: Path,
    ) -> Tuple[str, int, int]:
        """
        Uploads all files generated in source_dir (e.g. /workspace/output) into project's target tier partition.
        Returns: (primary_storage_uri, total_records, total_size_bytes)
        """
        now = datetime.now(timezone.utc)
        prefix = self.get_tier_prefix(project_id, target_tier, target_dataset)
        date_partition = f"year={now.year:04d}/month={now.month:02d}/day={now.day:02d}"

        total_records = 0
        total_size = 0
        primary_uri = f"s3://{self.bucket}/{prefix}"

        files = [p for p in source_dir.glob("**/*") if p.is_file()]
        for f in files:
            size = f.stat().st_size
            total_size += size

            # Calculate records if parquet or csv
            if f.suffix == ".parquet":
                try:
                    table = pq.read_table(str(f))
                    total_records += table.num_rows
                except Exception:
                    pass
            elif f.suffix in (".csv", ".jsonl"):
                try:
                    with open(f, "rb") as fp:
                        total_records += max(1, fp.read().count(b"\n"))
                except Exception:
                    pass

            object_name = f"{prefix}{date_partition}/{f.name}"
            self.client.fput_object(self.bucket, object_name, str(f))
            primary_uri = f"s3://{self.bucket}/{object_name}"

        return primary_uri, total_records, total_size
