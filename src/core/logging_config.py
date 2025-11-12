"""Logging helpers for the MLStock application."""

from __future__ import annotations

import logging
import logging.config
from pathlib import Path
from typing import Optional

from .settings import get_settings


def configure_logging(name: str = "mlstock", level: str = "INFO") -> logging.Logger:
    """Configure console and file logging."""
    settings = get_settings()
    log_dir: Path = settings.paths.log_dir
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "mlstock.log"

    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s | %(levelname)8s | %(name)s | %(message)s",
            },
            "json": {
                "format": '{"ts": "%(asctime)s", "level": "%(levelname)s", '
                '"logger": "%(name)s", "message": "%(message)s"}',
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": level,
                "formatter": "default",
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": level,
                "formatter": "default",
                "filename": str(log_file),
                "maxBytes": 5 * 1024 * 1024,
                "backupCount": 5,
                "encoding": "utf-8",
            },
        },
        "loggers": {
            name: {
                "handlers": ["console", "file"],
                "level": level,
                "propagate": False,
            },
        },
    }

    logging.config.dictConfig(logging_config)
    logger = logging.getLogger(name)
    logger.debug("Logging initialized", extra={"log_file": str(log_file)})
    return logger


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Return a child logger after ensuring base configuration."""
    base = logging.getLogger("mlstock")
    if not base.handlers:
        configure_logging()
        base = logging.getLogger("mlstock")
    return base if name is None else base.getChild(name)
