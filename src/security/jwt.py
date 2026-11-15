from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
import jwt
from passlib.context import CryptContext
try:
    from src.config.settings import settings
except ImportError:
    from config.settings import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hashes a plaintext password using bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plaintext password against a bcrypt hash."""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(
    subject: str,
    username: str,
    roles: Optional[List[str]] = None,
    scopes: Optional[List[str]] = None,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Generates a signed JWT access token."""
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.jwt_expiration_minutes)

    payload: Dict[str, Any] = {
        "sub": subject,
        "username": username,
        "roles": roles or ["analyst"],
        "scopes": scopes or ["read", "write"],
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }

    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token


def decode_access_token(token: str) -> Dict[str, Any]:
    """Decodes and validates a signed JWT access token.
    
    Raises jwt.PyJWTError on invalid signature, expiration, or format.
    """
    payload = jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
        options={"verify_exp": True},
    )
    return payload
