-- PostgreSQL Schema Initializer for Simplified Artemis

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- 1. Data Pipelines Registration
CREATE TABLE IF NOT EXISTS pipelines (
    pipeline_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) UNIQUE NOT NULL,
    schedule VARCHAR(50),
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    last_status VARCHAR(20),
    last_run_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Seed default pipeline
INSERT INTO pipelines (name, schedule, status)
VALUES ('mqtt_to_minio', '*/1 * * * *', 'ACTIVE')
ON CONFLICT (name) DO NOTHING;

-- 2. Pipeline Execution Runs
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_name VARCHAR(100) NOT NULL,
    status VARCHAR(20) NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE,
    events_processed INTEGER DEFAULT 0,
    details JSONB
);

-- 3. AI Query Audit Log
CREATE TABLE IF NOT EXISTS ai_queries (
    query_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(64) NOT NULL,
    prompt TEXT NOT NULL,
    context_payload JSONB,
    response TEXT NOT NULL,
    model_used VARCHAR(64) NOT NULL,
    cached BOOLEAN DEFAULT FALSE,
    duration_ms INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_ai_queries_user ON ai_queries(user_id);
CREATE INDEX IF NOT EXISTS idx_ai_queries_created ON ai_queries(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_time ON pipeline_runs(started_at DESC);

-- 4. Multi-Project & Medallion Pipeline Entities (Feature 004)
CREATE TABLE IF NOT EXISTS projects (
    project_id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    description TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS project_pipelines (
    pipeline_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id VARCHAR(64) NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    name VARCHAR(128) NOT NULL,
    description TEXT,
    stage VARCHAR(32) NOT NULL DEFAULT 'BRONZE_TO_SILVER',
    script_content TEXT NOT NULL,
    docker_image VARCHAR(128) NOT NULL DEFAULT 'artemis-pipeline-runner:latest',
    version INTEGER NOT NULL DEFAULT 1,
    created_by VARCHAR(64) NOT NULL DEFAULT 'admin',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_project_pipeline_name UNIQUE (project_id, name)
);

CREATE TABLE IF NOT EXISTS project_pipeline_runs (
    run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id VARCHAR(64) NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    pipeline_id UUID NOT NULL REFERENCES project_pipelines(pipeline_id) ON DELETE CASCADE,
    status VARCHAR(32) NOT NULL DEFAULT 'PENDING',
    stage VARCHAR(32) NOT NULL,
    target_tier VARCHAR(32) NOT NULL DEFAULT 'SILVER',
    input_datasets JSONB DEFAULT '[]'::jsonb,
    target_dataset VARCHAR(128) NOT NULL,
    records_processed INTEGER DEFAULT 0,
    exit_code INTEGER,
    logs TEXT,
    details JSONB DEFAULT '{}'::jsonb,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS project_datasets (
    project_id VARCHAR(64) NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    dataset_id VARCHAR(128) NOT NULL,
    tier VARCHAR(32) NOT NULL DEFAULT 'BRONZE',
    dataset_type VARCHAR(32) NOT NULL DEFAULT 'PARQUET',
    storage_uri TEXT NOT NULL,
    size_bytes BIGINT DEFAULT 0,
    record_count BIGINT DEFAULT 0,
    last_modified TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (project_id, dataset_id, tier)
);

CREATE INDEX IF NOT EXISTS idx_project_pipelines_project ON project_pipelines(project_id);
CREATE INDEX IF NOT EXISTS idx_project_pipeline_runs_project ON project_pipeline_runs(project_id);
CREATE INDEX IF NOT EXISTS idx_project_pipeline_runs_pipe ON project_pipeline_runs(pipeline_id);
CREATE INDEX IF NOT EXISTS idx_project_pipeline_runs_time ON project_pipeline_runs(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_project_datasets_lookup ON project_datasets(project_id, tier);

-- 5. Knowledge Discovery Graph & Project Membership (Feature 005)
CREATE TABLE IF NOT EXISTS project_members (
    project_id VARCHAR(64) NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    user_id VARCHAR(64) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'member',
    added_by VARCHAR(64) NOT NULL DEFAULT 'admin',
    added_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (project_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_project_members_user ON project_members(user_id);
CREATE INDEX IF NOT EXISTS idx_project_members_project ON project_members(project_id);

CREATE TABLE IF NOT EXISTS kdg_index_jobs (
    job_id VARCHAR(64) PRIMARY KEY,
    project_id VARCHAR(64) NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    resource_id VARCHAR(128) NOT NULL,
    phase VARCHAR(32) NOT NULL DEFAULT 'structural',
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 1,
    error TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_kdg_index_jobs_project ON kdg_index_jobs(project_id);
CREATE INDEX IF NOT EXISTS idx_kdg_index_jobs_status ON kdg_index_jobs(status);

-- 6. Dataset & Query Data TTL Retention & Auto-Cleanup (Feature 009)
INSERT INTO pipelines (name, schedule, status)
VALUES ('retention_auto_cleanup', '*/5 * * * *', 'ACTIVE')
ON CONFLICT (name) DO NOTHING;

CREATE TABLE IF NOT EXISTS ttl_policies (
    policy_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id VARCHAR(64) REFERENCES projects(project_id) ON DELETE CASCADE,
    target_scope VARCHAR(32) NOT NULL,
    tier VARCHAR(32),
    dataset_id VARCHAR(128),
    query_artifact_type VARCHAR(32),
    ttl_expression VARCHAR(32) NOT NULL,
    ttl_seconds BIGINT,
    granularity VARCHAR(32) NOT NULL DEFAULT 'INGESTION_AGE',
    timestamp_column VARCHAR(128),
    grace_period_expression VARCHAR(32) NOT NULL DEFAULT '24h',
    grace_period_seconds BIGINT NOT NULL DEFAULT 86400,
    updated_by VARCHAR(64) NOT NULL DEFAULT 'admin',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_ttl_policies_scope ON ttl_policies (
    COALESCE(project_id, '__GLOBAL__'),
    target_scope,
    COALESCE(tier, ''),
    COALESCE(dataset_id, ''),
    COALESCE(query_artifact_type, '')
);

CREATE TABLE IF NOT EXISTS dataset_retention_states (
    project_id VARCHAR(64) NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    dataset_id VARCHAR(128) NOT NULL,
    tier VARCHAR(32) NOT NULL DEFAULT 'BRONZE',
    effective_policy_id UUID REFERENCES ttl_policies(policy_id) ON DELETE SET NULL,
    policy_source VARCHAR(32) NOT NULL DEFAULT 'TIER_DEFAULT',
    effective_ttl_expression VARCHAR(32) NOT NULL DEFAULT '30d',
    effective_ttl_seconds BIGINT,
    granularity VARCHAR(32) NOT NULL DEFAULT 'INGESTION_AGE',
    timestamp_column VARCHAR(128),
    grace_period_expression VARCHAR(32) NOT NULL DEFAULT '24h',
    grace_period_seconds BIGINT NOT NULL DEFAULT 86400,
    reference_timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE,
    soft_deleted_at TIMESTAMP WITH TIME ZONE,
    purge_after TIMESTAMP WITH TIME ZONE,
    purged_at TIMESTAMP WITH TIME ZONE,
    retention_hold BOOLEAN NOT NULL DEFAULT FALSE,
    hold_reason TEXT,
    held_by VARCHAR(64),
    lifecycle_status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE',
    last_error TEXT,
    last_evaluated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (project_id, dataset_id, tier)
);

CREATE INDEX IF NOT EXISTS idx_dataset_retention_status ON dataset_retention_states(project_id, lifecycle_status);
CREATE INDEX IF NOT EXISTS idx_dataset_retention_expires ON dataset_retention_states(expires_at);

CREATE TABLE IF NOT EXISTS dataset_partitions (
    partition_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id VARCHAR(64) NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    dataset_id VARCHAR(128) NOT NULL,
    tier VARCHAR(32) NOT NULL DEFAULT 'BRONZE',
    object_key TEXT NOT NULL,
    storage_uri TEXT NOT NULL,
    size_bytes BIGINT NOT NULL DEFAULT 0,
    record_count BIGINT NOT NULL DEFAULT 0,
    ingested_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    min_event_ts TIMESTAMP WITH TIME ZONE,
    max_event_ts TIMESTAMP WITH TIME ZONE,
    lifecycle_status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE',
    soft_deleted_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_dataset_partitions_lookup ON dataset_partitions(project_id, dataset_id, tier, lifecycle_status);

CREATE TABLE IF NOT EXISTS query_data_artifacts (
    artifact_id VARCHAR(128) PRIMARY KEY,
    project_id VARCHAR(64) REFERENCES projects(project_id) ON DELETE CASCADE,
    artifact_type VARCHAR(32) NOT NULL,
    storage_uri TEXT NOT NULL,
    source_datasets JSONB NOT NULL DEFAULT '[]'::jsonb,
    size_bytes BIGINT NOT NULL DEFAULT 0,
    ttl_expression VARCHAR(32) NOT NULL,
    ttl_seconds BIGINT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE,
    soft_deleted_at TIMESTAMP WITH TIME ZONE,
    purge_after TIMESTAMP WITH TIME ZONE,
    retention_hold BOOLEAN NOT NULL DEFAULT FALSE,
    lifecycle_status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE'
);

CREATE INDEX IF NOT EXISTS idx_query_artifacts_project ON query_data_artifacts(project_id, artifact_type, lifecycle_status);
CREATE INDEX IF NOT EXISTS idx_query_artifacts_expires ON query_data_artifacts(expires_at);

CREATE TABLE IF NOT EXISTS dataset_active_leases (
    lease_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id VARCHAR(64) NOT NULL,
    dataset_id VARCHAR(128) NOT NULL,
    operation_type VARCHAR(32) NOT NULL,
    holder_id VARCHAR(128) NOT NULL,
    acquired_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_dataset_leases_active ON dataset_active_leases(project_id, dataset_id, expires_at);

CREATE TABLE IF NOT EXISTS cleanup_job_runs (
    run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trigger_type VARCHAR(32) NOT NULL,
    project_id VARCHAR(64),
    initiated_by VARCHAR(64) NOT NULL DEFAULT 'system',
    status VARCHAR(32) NOT NULL DEFAULT 'RUNNING',
    datasets_evaluated INTEGER NOT NULL DEFAULT 0,
    datasets_soft_deleted INTEGER NOT NULL DEFAULT 0,
    datasets_purged INTEGER NOT NULL DEFAULT 0,
    partitions_compacted INTEGER NOT NULL DEFAULT 0,
    rows_pruned BIGINT NOT NULL DEFAULT 0,
    query_artifacts_purged INTEGER NOT NULL DEFAULT 0,
    graph_elements_pruned INTEGER NOT NULL DEFAULT 0,
    tombstones_created INTEGER NOT NULL DEFAULT 0,
    bytes_reclaimed BIGINT NOT NULL DEFAULT 0,
    skipped_held_count INTEGER NOT NULL DEFAULT 0,
    skipped_locked_count INTEGER NOT NULL DEFAULT 0,
    candidate_items JSONB NOT NULL DEFAULT '[]'::jsonb,
    errors JSONB NOT NULL DEFAULT '[]'::jsonb,
    started_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE,
    duration_ms INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_cleanup_runs_project ON cleanup_job_runs(project_id, started_at DESC);

CREATE TABLE IF NOT EXISTS lineage_tombstones (
    project_id VARCHAR(64) NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    dataset_id VARCHAR(128) NOT NULL,
    tier VARCHAR(32) NOT NULL,
    applied_ttl_expression VARCHAR(32) NOT NULL,
    purged_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    upstream_datasets JSONB NOT NULL DEFAULT '[]'::jsonb,
    downstream_datasets JSONB NOT NULL DEFAULT '[]'::jsonb,
    cleanup_run_id UUID REFERENCES cleanup_job_runs(run_id) ON DELETE SET NULL,
    PRIMARY KEY (project_id, dataset_id, tier)
);


