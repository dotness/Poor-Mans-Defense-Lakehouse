from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class PipelineCreateContract(BaseModel):
    name: str = Field(..., min_length=1, max_length=128, description="Human-readable pipeline name")
    description: Optional[str] = Field(default=None, description="Pipeline purpose description")
    stage: str = Field(default="BRONZE_TO_SILVER", description="Stage: INGESTION, BRONZE_TO_SILVER, SILVER_TO_GOLD, CUSTOM")
    script_content: str = Field(..., min_length=1, description="Python transformation script source")
    docker_image: str = Field(default="artemis-pipeline-runner:latest", description="Docker image tag for execution")


class PipelineUpdateContract(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    description: Optional[str] = None
    stage: Optional[str] = None
    script_content: Optional[str] = None
    docker_image: Optional[str] = None


class PipelineResponseContract(BaseModel):
    pipeline_id: str
    project_id: str
    name: str
    description: Optional[str] = None
    stage: str
    docker_image: str
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
    started_at: datetime
    completed_at: Optional[datetime] = None
