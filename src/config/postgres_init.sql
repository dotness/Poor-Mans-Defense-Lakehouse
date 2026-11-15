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

