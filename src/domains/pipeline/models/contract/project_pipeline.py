from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class PipelineCreateContract(BaseModel):
    name: str = Field(..., min_length=1, max_length=128, description="Human-readable pipeline name")
    description: Optional[str] = Field(default=None, description="Pipeline purpose description")
    stage: str = Field(default="BRONZE_TO_SILVER", description="Stage: INGESTION, BRONZE_TO_SILVER, SILVER_TO_GOLD, CUSTOM")
    script_content: str = Field(..., min_length=1, description="Python transformation script source")
    docker_image: str = Field(default="artemis-pipeline-runner:latest", description="Docker image tag for execution")
    default_cpu_limit: Optional[float] = Field(
        default=None,
        description="Optional per-pipeline default CPU allocation in fractional cores (e.g. 1.5)",
    )
    default_memory_limit: Optional[str] = Field(
        default=None,
        description="Optional per-pipeline default memory limit string (e.g. '1g', '512m')",
    )


class PipelineUpdateContract(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    description: Optional[str] = None
    stage: Optional[str] = None
    script_content: Optional[str] = None
    docker_image: Optional[str] = None
    default_cpu_limit: Optional[float] = Field(
        default=None,
        description="Optional updated pipeline default CPU allocation in cores",
    )
    default_memory_limit: Optional[str] = Field(
        default=None,
        description="Optional updated pipeline default memory limit string",
    )


class PipelineResponseContract(BaseModel):
    pipeline_id: str
    project_id: str
    name: str
    description: Optional[str] = None
    stage: str
    docker_image: str
    default_cpu_limit: Optional[float] = None
    default_memory_limit: Optional[str] = None
    version: int = 1
    created_by: str = "admin"
    created_at: datetime
    updated_at: datetime


class PipelineRunTriggerContract(BaseModel):
    input_data: Optional[Dict[str, Any]] = None
    input_datasets: List[str] = Field(default_factory=list, description="List of source datasets in project")
    target_dataset: str = Field(..., description="Destination dataset identifier")
    target_tier: str = Field(default="SILVER", description="BRONZE, SILVER, or GOLD")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Custom parameters injected to script environment")
    timeout_seconds: int = Field(default=300, ge=1, le=3600, description="Container execution timeout in seconds")
    cpu_limit: Optional[float] = Field(
        default=None,
        description="Optional per-run custom CPU allocation in fractional cores (e.g. 0.5, 2.5)",
    )
    memory_limit: Optional[str] = Field(
        default=None,
        description="Optional per-run custom memory allocation string (e.g. '512m', '2g')",
    )


class PipelineRunResponseContract(BaseModel):
    run_id: str
    project_id: str
    pipeline_id: str
    status: str  # PENDING, RUNNING, SUCCESS, FAILED, TIMED_OUT
    stage: str
    target_tier: str
    target_dataset: str
    records_processed: int = 0
    duration_ms: int = 0
    exit_code: Optional[int] = None
    logs: Optional[str] = None
    effective_cpu_limit: Optional[float] = None
    effective_memory_limit: Optional[str] = None
    requested_cpu_limit: Optional[float] = None
    requested_memory_limit: Optional[str] = None
    resource_clamped: bool = False
    details: Optional[Dict[str, Any]] = None
    started_at: datetime
    completed_at: Optional[datetime] = None
