from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class MemberContract(BaseModel):
    project_id: str = Field(..., description="Project identifier")
    user_id: str = Field(..., description="User identifier")
    role: str = Field(default="member", description="Role: owner, member")
    added_by: Optional[str] = Field(default=None, description="Username or ID of adding user")
    added_at: Optional[datetime] = Field(default=None, description="Timestamp added")


class MemberAddRequestContract(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=64, description="User identifier to add")
    role: str = Field(default="member", pattern=r"^(owner|member)$", description="Role: owner, member")
