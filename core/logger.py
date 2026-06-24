"""Structured logging for QE-MCP.

Reads two env vars:
- ``QE_MCP_LOG_FORMAT``:  ``json`` (default) or ``text``
- ``QE_MCP_LOG_LEVEL``:   any Python log level name, default ``INFO``
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone


class StructuredFormatter(logging.Formatter):
    """Formatter that outputs one JSON object per log record."""

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        log_entry = {
            "ts": datetime.now(tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "module": record.module,
            "msg": record.getMessage(),
        }
        return json.dumps(log_entry, default=str)


def get_logger(name: str) -> logging.Logger:
    """Return a configured :class:`logging.Logger`.

    The format and level are controlled by environment variables so they
    can be toggled without code changes.
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        # Already configured — avoid duplicate handlers on repeated calls.
        return logger

    log_format = os.environ.get("QE_MCP_LOG_FORMAT", "json").lower()
    log_level_name = os.environ.get("QE_MCP_LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)

    handler = logging.StreamHandler()

    if log_format == "json":
        handler.setFormatter(StructuredFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        )

    logger.addHandler(handler)
    logger.setLevel(log_level)
    logger.propagate = False
    return logger
