import io
import json
from datetime import datetime, timedelta, timezone

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
except ImportError:
    pa = None
    pq = None

from src.domains.retention.models.contract.retention import DatasetPartitionContract
from src.domains.retention.operations.parquet_compactor import (
    ParquetCompactor,
    extract_parquet_timestamp_bounds,
)


class FakeMinioResponse:
    def __init__(self, data: bytes):
        self._buf = io.BytesIO(data)

    def read(self) -> bytes:
        return self._buf.getvalue()

    def close(self):
        pass

    def release_conn(self):
        pass


class FakeMinioClient:
    def __init__(self):
        self.objects = {}

    def put_object(self, bucket_name, object_name, data, length, content_type=None):
        self.objects[object_name] = data.read()

    def get_object(self, bucket_name, object_name):
        return FakeMinioResponse(self.objects[object_name])

    def remove_object(self, bucket_name, object_name):
        self.objects.pop(object_name, None)


class FakeS3Storage:
    def __init__(self):
        self.bucket = "telemetry"
        self.client = FakeMinioClient()


def _build_parquet_bytes(timestamps_iso):
    if pa is not None and pq is not None:
        table = pa.table(
            {
                "event_id": [f"ev-{i}" for i in range(len(timestamps_iso))],
                "event_ts": timestamps_iso,
                "value": [float(i * 10) for i in range(len(timestamps_iso))],
            }
        )
        sink = io.BytesIO()
        pq.write_table(table, sink)
        return sink.getvalue(), table
    rows = [
        {"event_id": f"ev-{i}", "event_ts": ts, "value": float(i * 10)}
        for i, ts in enumerate(timestamps_iso)
    ]
    return json.dumps(rows).encode("utf-8"), rows


def test_extract_timestamp_bounds_and_compact_table_bytes():
    raw_bytes, table = _build_parquet_bytes(
        [
            "2026-11-01T00:00:00Z",
            "2026-11-05T00:00:00Z",
            "2026-11-10T00:00:00Z",
            "2026-11-15T00:00:00Z",
        ]
    )
    min_ts, max_ts = extract_parquet_timestamp_bounds(table, "event_ts")
    assert min_ts == datetime(2026, 11, 1, 0, 0, 0, tzinfo=timezone.utc)
    assert max_ts == datetime(2026, 11, 15, 0, 0, 0, tzinfo=timezone.utc)

    compactor = ParquetCompactor(s3_storage=FakeS3Storage())
    cutoff = datetime(2026, 11, 8, 0, 0, 0, tzinfo=timezone.utc)
    compacted_bytes, rows_before, rows_after, new_min, new_max = compactor.compact_table_bytes(
        parquet_bytes=raw_bytes,
        timestamp_column="event_ts",
        active_cutoff_utc=cutoff,
    )
    assert rows_before == 4
    assert rows_after == 2
    assert compacted_bytes is not None
    assert new_min == datetime(2026, 11, 10, 0, 0, 0, tzinfo=timezone.utc)
    assert new_max == datetime(2026, 11, 15, 0, 0, 0, tzinfo=timezone.utc)


def test_s3_partition_compaction_defers_during_grace_and_compacts_after():
    fake_s3 = FakeS3Storage()
    compactor = ParquetCompactor(s3_storage=fake_s3)

    raw_bytes, table = _build_parquet_bytes(
        [
            "2026-11-01T00:00:00Z",
            "2026-11-05T00:00:00Z",
            "2026-11-10T00:00:00Z",
        ]
    )
    obj_key = "projects/alpha/bronze/events/batch_1.parquet"
    fake_s3.client.objects[obj_key] = raw_bytes
    min_ts, max_ts = extract_parquet_timestamp_bounds(table, "event_ts")

    part = DatasetPartitionContract(
        partition_id="p-1",
        project_id="alpha",
        dataset_id="events",
        tier="BRONZE",
        object_key=obj_key,
        storage_uri=f"s3://telemetry/{obj_key}",
        size_bytes=len(raw_bytes),
        record_count=3,
        ingested_at=datetime(2026, 11, 10, 0, 0, 0, tzinfo=timezone.utc),
        min_event_ts=min_ts,
        max_event_ts=max_ts,
    )

    # 1. When min_event_ts (Nov 1) is still >= purge_cutoff (Oct 31), NO_OP (still in virtual grace period)
    res_grace = compactor.compact_s3_partition(
        partition=part,
        timestamp_column="event_ts",
        active_cutoff_utc=datetime(2026, 11, 2, 0, 0, 0, tzinfo=timezone.utc),
        purge_cutoff_utc=datetime(2026, 10, 31, 0, 0, 0, tzinfo=timezone.utc),
    )
    assert res_grace.action == "NO_OP"
    assert obj_key in fake_s3.client.objects

    # 2. When min_event_ts (Nov 1) < purge_cutoff (Nov 3) and active_cutoff is Nov 4 -> compacts file!
    res_compact = compactor.compact_s3_partition(
        partition=part,
        timestamp_column="event_ts",
        active_cutoff_utc=datetime(2026, 11, 4, 0, 0, 0, tzinfo=timezone.utc),
        purge_cutoff_utc=datetime(2026, 11, 3, 0, 0, 0, tzinfo=timezone.utc),
    )
    assert res_compact.action == "COMPACTED"
    assert res_compact.rows_pruned == 1
    assert res_compact.rows_after == 2
    assert obj_key not in fake_s3.client.objects
    assert res_compact.new_object_key in fake_s3.client.objects

    # 3. When max_event_ts (Nov 10) < purge_cutoff (Nov 12) -> drops entire file!
    part2 = DatasetPartitionContract(
        partition_id="p-2",
        project_id="alpha",
        dataset_id="events",
        tier="BRONZE",
        object_key=res_compact.new_object_key,
        storage_uri=res_compact.new_storage_uri,
        size_bytes=res_compact.bytes_after,
        record_count=2,
        ingested_at=datetime(2026, 11, 10, 0, 0, 0, tzinfo=timezone.utc),
        min_event_ts=res_compact.new_min_event_ts,
        max_event_ts=res_compact.new_max_event_ts,
    )
    res_drop = compactor.compact_s3_partition(
        partition=part2,
        timestamp_column="event_ts",
        active_cutoff_utc=datetime(2026, 11, 13, 0, 0, 0, tzinfo=timezone.utc),
        purge_cutoff_utc=datetime(2026, 11, 12, 0, 0, 0, tzinfo=timezone.utc),
    )
    assert res_drop.action == "DROPPED_ENTIRE_FILE"
    assert res_drop.rows_pruned == 2
    assert len(fake_s3.client.objects) == 0
