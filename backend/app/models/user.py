"""User persistence model."""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import TimestampedModel


class User(TimestampedModel):
    """Application user account."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
