from contextvars import ContextVar
from typing import Optional, Dict, Any
from fastapi import Request, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt

try:
    from src.security.jwt import decode_access_token
except ImportError:
    from security.jwt import decode_access_token

# ContextVar storing the authenticated user profile for the current request thread/task
current_user: ContextVar[Optional[Dict[str, Any]]] = ContextVar("current_user", default=None)

security_scheme = HTTPBearer(auto_error=False)


def get_current_user() -> Optional[Dict[str, Any]]:
    """Retrieves the active user context from ContextVar."""
    return current_user.get()


async def authenticate_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
) -> Dict[str, Any]:
    """FastAPI dependency to extract, validate, and set the JWT user context.
    
    If credentials header is absent, attempts to inspect Authorization header manually.
    """
    token = None
    if credentials:
        token = credentials.credentials
    elif "Authorization" in request.headers:
        auth_header = request.headers["Authorization"]
        if auth_header.startswith("Bearer "):
            token = auth_header[len("Bearer "):].strip()

    # Public endpoint check (e.g. /api/v1/auth/token, /docs, /openapi.json, /health)
    path = request.url.path
    if path in ("/api/v1/auth/token", "/docs", "/openapi.json", "/health", "/"):
        return {"sub": "anonymous", "username": "anonymous", "roles": ["anonymous"]}

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Bearer authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.PyJWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication token: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_info = {
        "id": payload.get("sub"),
        "username": payload.get("username"),
        "roles": payload.get("roles", []),
        "scopes": payload.get("scopes", []),
    }

    current_user.set(user_info)
    return user_info
