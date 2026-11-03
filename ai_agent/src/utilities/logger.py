import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict


class JSONFormatter(logging.Formatter):
    """Formatter that outputs structured JSON log records."""

    def format(self, record: logging.LogRecord) -> str:
        log_data: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "funcName": record.funcName,
            "line": record.lineno,
        }

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        standard_attrs = {
            "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
            "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
            "created", "msecs", "relativeCreated", "thread", "threadName",
            "processName", "process", "message"
        }
        extra_data = {k: v for k, v in record.__dict__.items() if k not in standard_attrs}
        if extra_data:
            log_data["extra"] = extra_data

        return json.dumps(log_data)


def setup_json_logging(level: str | None = None) -> None:
    """Sets up application-wide JSON logging."""
    log_level_name = level or os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)

    root = logging.getLogger()
    root.setLevel(log_level)
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)
    handler.setFormatter(JSONFormatter())
    root.addHandler(handler)


setup_json_logging()


def get_logger(name: str = "ai_agent") -> logging.Logger:
    """Returns a logger instance configured for JSON logging."""
    return logging.getLogger(name)

