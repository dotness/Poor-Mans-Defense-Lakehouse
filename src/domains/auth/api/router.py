from fastapi import APIRouter, HTTPException, status
from src.domains.auth.facade.auth import AuthFacade
from src.domains.auth.models.contract.user import LoginRequestContract, TokenResponseContract

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


@router.post("/token", response_model=TokenResponseContract)
async def login(credentials: LoginRequestContract):
    """Issues a JWT token upon successful authentication."""
    facade = AuthFacade()
    try:
        token_resp = await facade.authenticate(credentials.username, credentials.password)
        return token_resp
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )
