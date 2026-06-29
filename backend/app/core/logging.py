"""Structured logging setup for API and worker processes."""

import logging
import sys


def configure_logging(level: str) -> None:
    """Configure process-wide logging with consistent structured fields."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
        force=True,
    )


def get_logger(name: str) -> logging.Logger:
    """Return a named application logger."""
    return logging.getLogger(name)
