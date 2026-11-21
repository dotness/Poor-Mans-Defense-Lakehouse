import re
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from src.domains.retention.operations.retention_repository import RetentionRepository
from src.domains.retention.operations.policy_resolver import PolicyResolver

logger = logging.getLogger("artemis.retention.query_interceptor")

# Matches read_parquet('s3://...') or read_parquet("s3://...")
_READ_PARQUET_REGEX = re.compile(
    r"read_parquet\s*\(\s*(['\"])(s3://[^'\"]+)\1\s*\)",
    re.IGNORECASE,
)

# Extracts project_id, optional tier, and optional dataset_id from S3 path
_PROJECT_PATH_REGEX = re.compile(
    r"^s3://[^/]+/projects/([a-zA-Z0-9_\-]+)(?:/([a-zA-Z0-9_\-\*]+))?(?:/([a-zA-Z0-9_\-\*]+))?",
    re.IGNORECASE,
)


@dataclass
class SQLInterceptionResult:
    rewritten_sql: str
    short_circuit_empty: bool = False
    empty_reason: Optional[str] = None
    referenced_datasets: List[Dict[str, str]] = field(default_factory=list)


class QueryTTLInterceptor:
    """
    Transparently intercepts DuckDB SQL and Memgraph Cypher queries at read time (FR-005):
    - Excludes expired or SOFT_DELETED / PURGED dataset partitions from S3 path/glob resolution.
    - Wraps read_parquet(...) calls on TIMESTAMP_COLUMN datasets with a timestamp cutoff predicate.
    - Filters expired or SOFT_DELETED graph datasets out of Cypher queries.
    """

    def __init__(
        self,
        repository: Optional[RetentionRepository] = None,
        policy_resolver: Optional[PolicyResolver] = None,
    ):
        self.repo = repository or RetentionRepository()
        self.resolver = policy_resolver or PolicyResolver(repository=self.repo)

    def _is_partition_active(
        self,
        part_ingested_at: datetime,
        part_status: str,
        ttl_seconds: Optional[int],
        retention_hold: bool,
        granularity: str,
        max_event_ts: Optional[datetime],
        now: datetime,
    ) -> bool:
        if part_status != "ACTIVE":
            return False
        if retention_hold or ttl_seconds is None:
            return True

        if granularity == "TIMESTAMP_COLUMN":
            # If max_event_ts is known and even the newest row in the file is older than cutoff, exclude file
            if max_event_ts is not None:
                m_ts = max_event_ts if max_event_ts.tzinfo else max_event_ts.replace(tzinfo=timezone.utc)
                if m_ts < (now - timedelta(seconds=ttl_seconds)):
                    return False
            return True

        # INGESTION_AGE granularity
        ing_ts = part_ingested_at if part_ingested_at.tzinfo else part_ingested_at.replace(tzinfo=timezone.utc)
        return (ing_ts + timedelta(seconds=ttl_seconds)) > now

    def _is_dataset_state_active(self, state, now: datetime) -> bool:
        if state.lifecycle_status in ("SOFT_DELETED", "PURGED"):
            return False
        if state.retention_hold or state.effective_ttl_seconds is None:
            return True
        if state.granularity == "INGESTION_AGE" and state.expires_at is not None:
            exp = state.expires_at if state.expires_at.tzinfo else state.expires_at.replace(tzinfo=timezone.utc)
            if exp <= now:
                return False
        return True

    def intercept_sql_query(
        self,
        sql: str,
        default_project_id: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> SQLInterceptionResult:
        """
        Inspects and rewrites a DuckDB SQL query to enforce dataset/partition and row-level TTLs at read time.
        """
        ref_now = now or datetime.now(timezone.utc)
        matches = list(_READ_PARQUET_REGEX.finditer(sql))
        if not matches:
            return SQLInterceptionResult(rewritten_sql=sql)

        referenced: List[Dict[str, str]] = []
        rewritten = sql
        # Replace from right to left so string offsets remain valid
        for m in reversed(matches):
            s3_uri = m.group(2)
            path_match = _PROJECT_PATH_REGEX.match(s3_uri)
            if not path_match:
                continue

            proj_id = path_match.group(1) or default_project_id
            tier_seg = path_match.group(2)
            ds_seg = path_match.group(3)
            if not proj_id:
                continue

            tier_filter = None if (not tier_seg or "*" in tier_seg) else tier_seg.upper()
            ds_filter = None if (not ds_seg or "*" in ds_seg or ds_seg.endswith(".parquet")) else ds_seg

            states = self.repo.list_dataset_states(project_id=proj_id)
            if tier_filter:
                states = [s for s in states if s.tier.upper() == tier_filter]
            if ds_filter:
                states = [s for s in states if s.dataset_id == ds_filter]

            # If no retention states are registered for this project/filter yet, leave query untouched
            if not states:
                if ds_filter:
                    referenced.append({"project_id": proj_id, "dataset_id": ds_filter, "tier": tier_filter or "BRONZE"})
                continue

            active_uris: List[str] = []
            ts_predicates: List[Tuple[str, datetime]] = []
            any_registered_partitions = False

            for st in states:
                referenced.append({"project_id": st.project_id, "dataset_id": st.dataset_id, "tier": st.tier})
                if not self._is_dataset_state_active(st, ref_now):
                    continue

                parts = self.repo.list_partitions(
                    project_id=st.project_id,
                    dataset_id=st.dataset_id,
                    tier=st.tier,
                )
                if parts:
                    any_registered_partitions = True
                    for p in parts:
                        if self._is_partition_active(
                            part_ingested_at=p.ingested_at,
                            part_status=p.lifecycle_status,
                            ttl_seconds=st.effective_ttl_seconds,
                            retention_hold=st.retention_hold,
                            granularity=st.granularity,
                            max_event_ts=p.max_event_ts,
                            now=ref_now,
                        ):
                            active_uris.append(p.storage_uri)
                else:
                    # State is active, no individual partition records tracked — allow original URI
                    active_uris.append(s3_uri)

                if (
                    st.granularity == "TIMESTAMP_COLUMN"
                    and st.timestamp_column
                    and not st.retention_hold
                    and st.effective_ttl_seconds is not None
                ):
                    cutoff = ref_now - timedelta(seconds=st.effective_ttl_seconds)
                    ts_predicates.append((st.timestamp_column, cutoff))

            # If all matched datasets or all their tracked partitions are expired/SOFT_DELETED, short-circuit!
            if not active_uris:
                return SQLInterceptionResult(
                    rewritten_sql=rewritten,
                    short_circuit_empty=True,
                    empty_reason=f"All target datasets or partitions for '{s3_uri}' have expired under active TTL policies.",
                    referenced_datasets=referenced,
                )

            # Build replacement read_parquet expression
            unique_uris = list(dict.fromkeys(active_uris))
            if any_registered_partitions and (len(unique_uris) != 1 or unique_uris[0] != s3_uri):
                if len(unique_uris) == 1:
                    rp_expr = f"read_parquet('{unique_uris[0]}')"
                else:
                    uris_literal = ", ".join(f"'{u}'" for u in unique_uris)
                    rp_expr = f"read_parquet([{uris_literal}])"
            else:
                rp_expr = f"read_parquet('{s3_uri}')"

            # Wrap in row-level timestamp predicate if TIMESTAMP_COLUMN is active
            if ts_predicates:
                col_name, cutoff_dt = ts_predicates[0]
                safe_col = re.sub(r'[^a-zA-Z0-9_]', '', col_name)
                cutoff_iso = cutoff_dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                rp_expr = (
                    f"(SELECT * FROM {rp_expr} "
                    f"WHERE TRY_CAST(\"{safe_col}\" AS TIMESTAMPTZ) >= TIMESTAMPTZ '{cutoff_iso}')"
                )

            start_idx, end_idx = m.span()
            rewritten = rewritten[:start_idx] + rp_expr + rewritten[end_idx:]

        return SQLInterceptionResult(
            rewritten_sql=rewritten,
            short_circuit_empty=False,
            referenced_datasets=referenced,
        )

    def get_expired_or_soft_deleted_datasets(
        self,
        project_id: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> Set[Tuple[str, str]]:
        """Returns a set of (project_id, dataset_id) pairs that are currently expired, SOFT_DELETED, or PURGED."""
        ref_now = now or datetime.now(timezone.utc)
        states = self.repo.list_dataset_states(project_id=project_id)
        excluded: Set[Tuple[str, str]] = set()
        for st in states:
            if not self._is_dataset_state_active(st, ref_now):
                excluded.add((st.project_id, st.dataset_id))
        return excluded

    def filter_graph_records(
        self,
        records: List[Dict[str, Any]],
        project_id: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Filters out Memgraph result records belonging to expired or SOFT_DELETED datasets."""
        excluded = self.get_expired_or_soft_deleted_datasets(project_id=project_id, now=now)
        if not excluded:
            return records

        filtered: List[Dict[str, Any]] = []
        for rec in records:
            rec_proj = rec.get("project_id") or project_id
            rec_ds = rec.get("resource_id") or rec.get("dataset_id")
            if rec_proj and rec_ds and (rec_proj, rec_ds) in excluded:
                continue
            # Also check nested node dicts
            skip = False
            for val in rec.values():
                if isinstance(val, dict):
                    vp = val.get("project_id") or project_id
                    vd = val.get("resource_id") or val.get("dataset_id")
                    v_status = val.get("lifecycle_status")
                    if v_status in ("SOFT_DELETED", "PURGED"):
                        skip = True
                        break
                    if vp and vd and (vp, vd) in excluded:
                        skip = True
                        break
            if not skip:
                filtered.append(rec)
        return filtered
