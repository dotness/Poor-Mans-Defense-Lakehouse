import logging
from typing import Optional
from src.base.facade import DomainFacade, ResourceDoesNotExist
from src.domains.auth.models.contract.user import UserInfoContract, TokenResponseContract
from src.security.jwt import create_access_token, decode_access_token

logger = logging.getLogger(__name__)

# Predefined development users
DEV_USERS = {
    "admin": {
        "id": "usr-admin-001",
        "username": "admin",
        "passwords": ["admin", "admin_password"],
        "roles": ["admin", "analyst"],
        "scopes": ["read", "write", "admin"],
    },
    "analyst": {
        "id": "usr-analyst-002",
        "username": "analyst",
        "passwords": ["analyst", "analyst_password"],
        "roles": ["analyst"],
        "scopes": ["read", "write"],
    },
}


class AuthFacade(DomainFacade):
    """Facade for user authentication and authorization."""

    async def authenticate(self, username: str, password: str) -> TokenResponseContract:
        """Validates credentials and returns a signed JWT token response."""
        user_record = DEV_USERS.get(username)
        if not user_record or password not in user_record.get("passwords", []):
            raise PermissionError("Invalid username or password")

        user_info = UserInfoContract(
            id=user_record["id"],
            username=user_record["username"],
            roles=user_record["roles"],
            scopes=user_record["scopes"],
        )

        token = create_access_token(
            subject=user_info.id,
            username=user_info.username,
            roles=user_info.roles,
            scopes=user_info.scopes,
        )

        return TokenResponseContract(
            access_token=token,
            user=user_info,
        )

    async def verify_token(self, token: str) -> UserInfoContract:
        """Validates a JWT token and returns user info contract."""
        payload = decode_access_token(token)
        return UserInfoContract(
            id=payload["sub"],
            username=payload["username"],
            roles=payload.get("roles", ["analyst"]),
            scopes=payload.get("scopes", ["read"]),
        )
