from typing import List, Optional
from pydantic import BaseModel, Field


class UserInfoContract(BaseModel):
    id: str
    username: str
    roles: List[str] = Field(default_factory=lambda: ["analyst"])
    scopes: List[str] = Field(default_factory=lambda: ["read", "write"])


class LoginRequestContract(BaseModel):
    username: str
    password: str


class TokenResponseContract(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int = 86400  # seconds (24h)
    user: UserInfoContract
