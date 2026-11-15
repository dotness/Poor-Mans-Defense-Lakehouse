import io
import json
import uuid
import logging
from datetime import datetime, timezone
from typing import List, Optional
import pyarrow as pa
import pyarrow.parquet as pq
from minio import Minio

try:
    from src.config.settings import settings
    from src.services.ingestion.models import TelemetryEvent
except ImportError:
    from config.settings import settings
    from services.ingestion.models import TelemetryEvent

logger = logging.getLogger("artemis.ingestion.minio")

PARQUET_SCHEMA = pa.schema([
    ("event_id", pa.string()),
    ("timestamp", pa.timestamp("us", tz="UTC")),
    ("device_id", pa.string()),
    ("metric_name", pa.string()),
    ("value", pa.float64()),
    ("unit", pa.string()),
    ("metadata", pa.string()),
])


class MinioParquetWriter:
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
            logger.warning(f"Could not ensure MinIO bucket '{self.bucket}': {e}")

    def write_batch(self, events: List[TelemetryEvent]) -> Optional[str]:
        if not events:
            return None

        now = datetime.now(timezone.utc)
        record_data = {
            "event_id": [e.event_id for e in events],
            "timestamp": [e.timestamp for e in events],
            "device_id": [e.device_id for e in events],
            "metric_name": [e.metric_name for e in events],
            "value": [e.value for e in events],
            "unit": [e.unit for e in events],
            "metadata": [json.dumps(e.metadata) for e in events],
        }

        table = pa.Table.from_pydict(record_data, schema=PARQUET_SCHEMA)
        sink = io.BytesIO()
        pq.write_table(table, sink, compression="SNAPPY")
        sink.seek(0)
        size = sink.getbuffer().nbytes

        object_key = (
            f"year={now.year:04d}/month={now.month:02d}/day={now.day:02d}/"
            f"batch_{int(now.timestamp())}_{uuid.uuid4().hex[:8]}.parquet"
        )

        self.client.put_object(
            bucket_name=self.bucket,
            object_name=object_key,
            data=sink,
            length=size,
            content_type="application/octet-stream",
        )
        logger.info(f"Flushed {len(events)} events to MinIO: s3://{self.bucket}/{object_key}")
        return object_key
