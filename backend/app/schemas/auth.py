"""Authentication request and response schemas."""

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    """Credentials submitted for authentication."""

    email: EmailStr
    password: str = Field(min_length=12)


class TokenResponse(BaseModel):
    """JWT response returned after successful authentication."""

    access_token: str
    token_type: str = "bearer"
