from typing import Any, List, Optional
from pydantic import BaseModel, Field


class QueryRequestContract(BaseModel):
    sql: str
    format: str = "table"  # table | json | csv
    cache_ttl: Optional[str] = None
    export_dataset: Optional[str] = None
    export_ttl: Optional[str] = None


class QueryResultContract(BaseModel):
    columns: List[str] = Field(default_factory=list)
    rows: List[List[Any]] = Field(default_factory=list)
    row_count: int = 0
    duration_ms: int = 0
    formatted_output: Optional[str] = None
    cached: bool = False
    export_artifact_id: Optional[str] = None
