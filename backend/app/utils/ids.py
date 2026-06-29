"""Identifier helpers."""

from uuid import UUID


def parse_uuid(value: str) -> UUID:
    """Parse a UUID string and raise a clear ValueError on failure."""
    try:
        return UUID(value)
    except ValueError as exc:
        raise ValueError(f"Invalid UUID: {value}") from exc
