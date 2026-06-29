"""Reusable FastAPI dependency providers."""

from uuid import UUID

from fastapi import Header, HTTPException, status

from app.core.errors import AuthenticationError
from app.core.security import decode_access_token


async def current_user_id(authorization: str = Header(default="")) -> UUID:
    """Resolve the authenticated user id from a bearer token."""
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    try:
        payload = decode_access_token(token)
        return UUID(payload["sub"])
    except (AuthenticationError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token") from exc
