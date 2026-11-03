"""Structured JSON logging utility for the Maritime Assistant system.
Adheres to SOLID principles: Single responsibility for formatting and managing structured logs.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from utility.config import get_config


class JSONFormatter(logging.Formatter):
    """Formatter that outputs structured JSON log records with standard metadata."""

    _STANDARD_ATTRS = {
        "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
        "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
        "created", "msecs", "relativeCreated", "thread", "threadName",
        "processName", "process", "message"
    }

    def format(self, record: logging.LogRecord) -> str:
        log_data: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "func_name": record.funcName,
            "line": record.lineno,
        }

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Collect structured extra fields passed by callers: logger.info("...", extra={...})
        extra_data = {
            k: v for k, v in record.__dict__.items()
            if k not in self._STANDARD_ATTRS and not k.startswith("_")
        }
        if extra_data:
            log_data["extra"] = extra_data

        return json.dumps(log_data, default=str)


def setup_json_logging(level: Optional[str] = None) -> None:
    """Configures application-wide structured JSON logging on sys.stdout."""
    config = get_config()
    log_level_name = (level or config.logging.level).upper()
    log_level = getattr(logging, log_level_name, logging.INFO)

    root = logging.getLogger()
    root.setLevel(log_level)

    # Avoid duplicate handlers if setup is called multiple times
    for handler in list(root.handlers):
        root.removeHandler(handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(log_level)
    stream_handler.setFormatter(JSONFormatter())
    root.addHandler(stream_handler)


# Auto-configure logging on module load
setup_json_logging()


def get_logger(name: str = "maritime_kg") -> logging.Logger:
    """Provides a named logger instance configured for JSON structured logging."""
    return logging.getLogger(name)

