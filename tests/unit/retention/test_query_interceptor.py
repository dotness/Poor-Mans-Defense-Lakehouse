from datetime import datetime, timedelta, timezone
from src.domains.retention.models.contract.retention import DatasetTTLSetRequestContract
from src.domains.retention.operations.policy_resolver import PolicyResolver
from src.domains.retention.operations.query_interceptor import QueryTTLInterceptor
from tests.unit.retention.test_policy_resolver import InMemoryRetentionRepository


def test_interceptor_short_circuits_expired_whole_dataset():
    repo = InMemoryRetentionRepository()
    resolver = PolicyResolver(repository=repo)
    interceptor = QueryTTLInterceptor(repository=repo, policy_resolver=resolver)

    t0 = datetime(2026, 11, 1, 0, 0, 0, tzinfo=timezone.utc)
    repo.add_partition(
        project_id="alpha",
        dataset_id="metrics",
        tier="BRONZE",
        object_key="projects/alpha/bronze/metrics/part1.parquet",
        storage_uri="s3://telemetry/projects/alpha/bronze/metrics/part1.parquet",
        size_bytes=1024,
        record_count=10,
        ingested_at=t0,
    )
    resolver.set_dataset_ttl(
        "alpha",
        "metrics",
        DatasetTTLSetRequestContract(tier="BRONZE", ttl_expression="1d"),
        now=t0,
    )

    sql = "SELECT * FROM read_parquet('s3://telemetry/projects/alpha/bronze/metrics/*.parquet')"

    # 1. Before expiration (t0 + 12h): query proceeds normally
    res_active = interceptor.intercept_sql_query(sql, now=t0 + timedelta(hours=12))
    assert res_active.short_circuit_empty is False
    assert "part1.parquet" in res_active.rewritten_sql

    # 2. After expiration (t0 + 2 days): query short-circuits immediately
    res_expired = interceptor.intercept_sql_query(sql, now=t0 + timedelta(days=2))
    assert res_expired.short_circuit_empty is True
    assert "expired" in (res_expired.empty_reason or "").lower()


def test_interceptor_filters_only_active_partitions_on_append():
    repo = InMemoryRetentionRepository()
    resolver = PolicyResolver(repository=repo)
    interceptor = QueryTTLInterceptor(repository=repo, policy_resolver=resolver)

    t0 = datetime(2026, 11, 1, 0, 0, 0, tzinfo=timezone.utc)
    t_fresh = t0 + timedelta(days=5)

    # Older file ingested at t0
    repo.add_partition(
        project_id="alpha",
        dataset_id="logs",
        tier="BRONZE",
        object_key="old.parquet",
        storage_uri="s3://telemetry/projects/alpha/bronze/logs/old.parquet",
        size_bytes=100,
        record_count=5,
        ingested_at=t0,
    )
    # Appended newer file ingested at t0 + 5d
    repo.add_partition(
        project_id="alpha",
        dataset_id="logs",
        tier="BRONZE",
        object_key="fresh.parquet",
        storage_uri="s3://telemetry/projects/alpha/bronze/logs/fresh.parquet",
        size_bytes=200,
        record_count=10,
        ingested_at=t_fresh,
    )
    resolver.set_dataset_ttl(
        "alpha",
        "logs",
        DatasetTTLSetRequestContract(tier="BRONZE", ttl_expression="3d"),
        now=t_fresh,
    )
    # Force dataset expires_at to reflect the newest partition so dataset as a whole is active
    st = repo.get_dataset_state("alpha", "logs", "BRONZE")
    st.expires_at = t_fresh + timedelta(days=3)
    repo.upsert_dataset_state(st)

    # Query at t0 + 6d: old.parquet (age 6d > 3d) is excluded, fresh.parquet (age 1d <= 3d) is included
    sql = "SELECT COUNT(*) FROM read_parquet('s3://telemetry/projects/alpha/bronze/logs/*.parquet')"
    res = interceptor.intercept_sql_query(sql, now=t0 + timedelta(days=6))
    assert res.short_circuit_empty is False
    assert "fresh.parquet" in res.rewritten_sql
    assert "old.parquet" not in res.rewritten_sql


def test_interceptor_injects_timestamp_column_predicate():
    repo = InMemoryRetentionRepository()
    resolver = PolicyResolver(repository=repo)
    interceptor = QueryTTLInterceptor(repository=repo, policy_resolver=resolver)

    t0 = datetime(2026, 11, 10, 12, 0, 0, tzinfo=timezone.utc)
    repo.add_partition(
        project_id="alpha",
        dataset_id="events",
        tier="BRONZE",
        object_key="events.parquet",
        storage_uri="s3://telemetry/projects/alpha/bronze/events/events.parquet",
        size_bytes=1000,
        record_count=100,
        ingested_at=t0,
    )
    resolver.set_dataset_ttl(
        "alpha",
        "events",
        DatasetTTLSetRequestContract(
            tier="BRONZE",
            ttl_expression="7d",
            granularity="TIMESTAMP_COLUMN",
            timestamp_column="event_ts",
        ),
        now=t0,
    )

    query_time = datetime(2026, 11, 15, 12, 0, 0, tzinfo=timezone.utc)
    sql = "SELECT device_id, COUNT(*) FROM read_parquet('s3://telemetry/projects/alpha/bronze/events/*.parquet') GROUP BY device_id"
    res = interceptor.intercept_sql_query(sql, now=query_time)
    assert res.short_circuit_empty is False
    assert 'TRY_CAST("event_ts" AS TIMESTAMPTZ) >= TIMESTAMPTZ \'2026-11-08T12:00:00Z\'' in res.rewritten_sql


def test_interceptor_filters_expired_graph_records():
    repo = InMemoryRetentionRepository()
    resolver = PolicyResolver(repository=repo)
    interceptor = QueryTTLInterceptor(repository=repo, policy_resolver=resolver)

    t0 = datetime(2026, 11, 1, 0, 0, 0, tzinfo=timezone.utc)
    st = resolver.set_dataset_ttl(
        "alpha",
        "expired_graph",
        DatasetTTLSetRequestContract(tier="BRONZE", ttl_expression="1d"),
        now=t0,
    )
    st.lifecycle_status = "SOFT_DELETED"
    repo.upsert_dataset_state(st)

    records = [
        {"project_id": "alpha", "resource_id": "expired_graph", "value": "stale-entity"},
        {"project_id": "alpha", "resource_id": "active_graph", "value": "valid-entity"},
    ]
    filtered = interceptor.filter_graph_records(records, project_id="alpha", now=t0 + timedelta(days=2))
    assert len(filtered) == 1
    assert filtered[0]["resource_id"] == "active_graph"
