"""Authentication endpoints."""

from fastapi import APIRouter, HTTPException, status

from app.schemas.auth import LoginRequest, TokenResponse

router = APIRouter(tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(_: LoginRequest) -> TokenResponse:
    """Authenticate a user and return an access token.

    Password verification is intentionally delegated to the future user repository
    implementation. Until a repository is configured, the endpoint rejects all
    credentials instead of pretending authentication succeeded.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="User credential repository is not configured",
    )
