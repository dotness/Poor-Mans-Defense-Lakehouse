from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, model_validator

from src.domains.retention.operations.ttl_parser import (
    parse_ttl_expression,
    normalize_ttl_expression,
)


TargetScopeType = Literal["PLATFORM", "PROJECT", "TIER", "DATASET", "QUERY_DATA"]
TierType = Literal["BRONZE", "SILVER", "GOLD"]
GranularityType = Literal["INGESTION_AGE", "TIMESTAMP_COLUMN"]
QueryArtifactCategoryType = Literal[
    "SQL_RESULT_CACHE",
    "AI_RAG_CACHE",
    "MATERIALIZED_EXPORT",
    "QUERY_HISTORY_LOG",
]
LifecycleStatusType = Literal[
    "ACTIVE",
    "EXPIRING_SOON",
    "HELD",
    "SOFT_DELETED",
    "CLEANUP_IN_PROGRESS",
    "CLEANUP_PENDING_RETRY",
    "PURGED",
]


class TTLPolicyContract(BaseModel):
    policy_id: Optional[str] = None
    project_id: Optional[str] = None
    target_scope: TargetScopeType = "DATASET"
    tier: Optional[str] = None
    dataset_id: Optional[str] = None
    query_artifact_type: Optional[str] = None
    ttl_expression: str = Field(..., description="Human-readable duration e.g. '30d', '24h', 'never'")
    ttl_seconds: Optional[int] = None
    granularity: GranularityType = "INGESTION_AGE"
    timestamp_column: Optional[str] = None
    grace_period_expression: str = "24h"
    grace_period_seconds: int = 86400
    updated_by: str = "admin"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class DatasetTTLSetRequestContract(BaseModel):
    tier: str = Field(default="BRONZE", description="Medallion tier: BRONZE, SILVER, GOLD")
    ttl_expression: str = Field(..., description="TTL duration expression e.g. '30d', '24h', '7d', 'never'")
    granularity: GranularityType = Field(default="INGESTION_AGE", description="INGESTION_AGE or TIMESTAMP_COLUMN")
    timestamp_column: Optional[str] = Field(default=None, description="Event timestamp column name when granularity is TIMESTAMP_COLUMN")
    grace_period_expression: str = Field(default="24h", description="Soft-delete grace period e.g. '24h' or '0h'")

    @model_validator(mode="after")
    def validate_fields(self) -> "DatasetTTLSetRequestContract":
        self.tier = self.tier.strip().upper()
        if self.tier not in ("BRONZE", "SILVER", "GOLD"):
            raise ValueError(f"Invalid tier '{self.tier}'. Must be BRONZE, SILVER, or GOLD.")
        # Validate ttl_expression (>0 or never)
        parse_ttl_expression(self.ttl_expression, allow_zero=False, allow_infinite=True)
        self.ttl_expression = normalize_ttl_expression(self.ttl_expression, allow_zero=False, allow_infinite=True)

        # Validate grace_period_expression (>=0, not infinite)
        parse_ttl_expression(self.grace_period_expression, allow_zero=True, allow_infinite=False)
        self.grace_period_expression = normalize_ttl_expression(
            self.grace_period_expression, allow_zero=True, allow_infinite=False
        )

        if self.granularity == "TIMESTAMP_COLUMN":
            if not self.timestamp_column or not self.timestamp_column.strip():
                raise ValueError("timestamp_column is required when granularity is TIMESTAMP_COLUMN.")
            self.timestamp_column = self.timestamp_column.strip()
        return self


class ProjectTTLDefaultsRequestContract(BaseModel):
    target_scope: Literal["PROJECT", "TIER", "QUERY_DATA"] = "TIER"
    tier: Optional[str] = None
    query_artifact_type: Optional[QueryArtifactCategoryType] = None
    ttl_expression: str
    grace_period_expression: str = "24h"

    @model_validator(mode="after")
    def validate_defaults(self) -> "ProjectTTLDefaultsRequestContract":
        parse_ttl_expression(self.ttl_expression, allow_zero=False, allow_infinite=True)
        self.ttl_expression = normalize_ttl_expression(self.ttl_expression, allow_zero=False, allow_infinite=True)

        parse_ttl_expression(self.grace_period_expression, allow_zero=True, allow_infinite=False)
        self.grace_period_expression = normalize_ttl_expression(
            self.grace_period_expression, allow_zero=True, allow_infinite=False
        )

        if self.target_scope == "TIER":
            if not self.tier:
                raise ValueError("tier is required when target_scope is TIER.")
            self.tier = self.tier.strip().upper()
            if self.tier not in ("BRONZE", "SILVER", "GOLD"):
                raise ValueError(f"Invalid tier '{self.tier}'.")
        elif self.target_scope == "QUERY_DATA":
            if not self.query_artifact_type:
                raise ValueError("query_artifact_type is required when target_scope is QUERY_DATA.")
        return self


class DatasetPartitionContract(BaseModel):
    partition_id: Optional[str] = None
    project_id: str
    dataset_id: str
    tier: str = "BRONZE"
    object_key: str
    storage_uri: str
    size_bytes: int = 0
    record_count: int = 0
    ingested_at: datetime
    min_event_ts: Optional[datetime] = None
    max_event_ts: Optional[datetime] = None
    lifecycle_status: str = "ACTIVE"
    soft_deleted_at: Optional[datetime] = None


class DatasetRetentionStateContract(BaseModel):
    project_id: str
    dataset_id: str
    tier: str = "BRONZE"
    effective_policy_id: Optional[str] = None
    policy_source: str = "TIER_DEFAULT"
    effective_ttl_expression: str = "30d"
    effective_ttl_seconds: Optional[int] = 2592000
    granularity: GranularityType = "INGESTION_AGE"
    timestamp_column: Optional[str] = None
    grace_period_expression: str = "24h"
    grace_period_seconds: int = 86400
    reference_timestamp: datetime
    expires_at: Optional[datetime] = None
    soft_deleted_at: Optional[datetime] = None
    purge_after: Optional[datetime] = None
    purged_at: Optional[datetime] = None
    retention_hold: bool = False
    hold_reason: Optional[str] = None
    held_by: Optional[str] = None
    lifecycle_status: str = "ACTIVE"
    last_error: Optional[str] = None
    last_evaluated_at: Optional[datetime] = None
    age_seconds: Optional[int] = None
    remaining_seconds: Optional[int] = None
    active_partitions_count: int = 0
    auto_restored: bool = False


class RetentionHoldRequestContract(BaseModel):
    tier: str = "BRONZE"
    retention_hold: bool = True
    reason: Optional[str] = None

    @model_validator(mode="after")
    def normalize_tier(self) -> "RetentionHoldRequestContract":
        self.tier = self.tier.strip().upper()
        return self


class DatasetRestoreRequestContract(BaseModel):
    tier: str = "BRONZE"
    ttl_expression: Optional[str] = None
    retention_hold: bool = False
    reason: Optional[str] = None

    @model_validator(mode="after")
    def validate_restore(self) -> "DatasetRestoreRequestContract":
        self.tier = self.tier.strip().upper()
        if not self.ttl_expression and not self.retention_hold:
            raise ValueError(
                "Restoring a SOFT_DELETED dataset requires either extending 'ttl_expression' or setting 'retention_hold=True'."
            )
        if self.ttl_expression:
            parse_ttl_expression(self.ttl_expression, allow_zero=False, allow_infinite=True)
            self.ttl_expression = normalize_ttl_expression(self.ttl_expression, allow_zero=False, allow_infinite=True)
        return self


class QueryDataArtifactContract(BaseModel):
    artifact_id: str
    project_id: Optional[str] = None
    artifact_type: QueryArtifactCategoryType
    storage_uri: str
    source_datasets: List[Dict[str, Any]] = Field(default_factory=list)
    size_bytes: int = 0
    ttl_expression: str
    ttl_seconds: Optional[int] = None
    created_at: datetime
    expires_at: Optional[datetime] = None
    soft_deleted_at: Optional[datetime] = None
    purge_after: Optional[datetime] = None
    retention_hold: bool = False
    lifecycle_status: str = "ACTIVE"


class ProjectRetentionSummaryContract(BaseModel):
    project_id: str
    default_policies: Dict[str, str]
    counts: Dict[str, int]
    datasets: List[Dict[str, Any]]
    query_artifacts_summary: Dict[str, Any]
    tombstones: List[Dict[str, Any]] = Field(default_factory=list)


class CleanupTriggerRequestContract(BaseModel):
    dry_run: bool = False
    include_query_artifacts: bool = True


class CleanupCandidateItemContract(BaseModel):
    item_type: Literal["DATASET", "PARTITION_COMPACTION", "QUERY_ARTIFACT"]
    project_id: Optional[str] = None
    dataset_id: Optional[str] = None
    tier: Optional[str] = None
    artifact_id: Optional[str] = None
    action: Literal["SOFT_DELETE", "PURGE", "COMPACT_ROWS", "SKIP_HELD", "SKIP_LOCKED"]
    bytes_reclaimed: int = 0
    rows_pruned: int = 0
    reason: str = ""


class CleanupJobRunContract(BaseModel):
    run_id: str
    trigger_type: Literal["SCHEDULED", "MANUAL", "DRY_RUN"]
    project_id: Optional[str] = None
    initiated_by: str = "system"
    status: Literal["RUNNING", "SUCCESS", "PARTIAL_FAILURE", "FAILED"] = "SUCCESS"
    datasets_evaluated: int = 0
    datasets_soft_deleted: int = 0
    datasets_purged: int = 0
    partitions_compacted: int = 0
    rows_pruned: int = 0
    query_artifacts_purged: int = 0
    graph_elements_pruned: int = 0
    tombstones_created: int = 0
    bytes_reclaimed: int = 0
    skipped_held_count: int = 0
    skipped_locked_count: int = 0
    candidate_items: List[Dict[str, Any]] = Field(default_factory=list)
    errors: List[Dict[str, Any]] = Field(default_factory=list)
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_ms: int = 0


class LineageTombstoneContract(BaseModel):
    project_id: str
    dataset_id: str
    tier: str
    applied_ttl_expression: str
    purged_at: datetime
    upstream_datasets: List[str] = Field(default_factory=list)
    downstream_datasets: List[str] = Field(default_factory=list)
    cleanup_run_id: Optional[str] = None
