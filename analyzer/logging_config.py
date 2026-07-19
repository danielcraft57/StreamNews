"""Configuration logging StreamNews (console + fichiers rotatifs dans logs/)."""
from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

_CONFIGURED = False

# analyzer/logging_config.py -> repo root = parents[1]
_REPO_ROOT = Path(__file__).resolve().parents[1]


def is_configured() -> bool:
    return _CONFIGURED


def logs_dir() -> Path:
    raw = os.getenv("LOG_DIR", "").strip()
    if raw:
        path = Path(raw)
    else:
        path = _REPO_ROOT / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def setup_logging(
    service: str = "analyzer",
    level: Optional[str] = None,
) -> logging.Logger:
    """
    Initialise le logging une seule fois.

    Fichiers :
      logs/{service}.log
      logs/errors.log  (WARNING+)
    """
    global _CONFIGURED
    root = logging.getLogger()
    if _CONFIGURED and root.handlers:
        return logging.getLogger(f"streamnews.{service}")

    level_name = (level or os.getenv("LOG_LEVEL", "INFO")).upper()
    log_level = getattr(logging, level_name, logging.INFO)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root.handlers.clear()
    root.setLevel(log_level)

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(log_level)
    console.setFormatter(fmt)
    root.addHandler(console)

    log_path = logs_dir() / f"{service}.log"
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=int(os.getenv("LOG_MAX_BYTES", str(5 * 1024 * 1024))),
        backupCount=int(os.getenv("LOG_BACKUP_COUNT", "5")),
        encoding="utf-8",
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    err_handler = RotatingFileHandler(
        logs_dir() / "errors.log",
        maxBytes=int(os.getenv("LOG_MAX_BYTES", str(5 * 1024 * 1024))),
        backupCount=int(os.getenv("LOG_BACKUP_COUNT", "5")),
        encoding="utf-8",
    )
    err_handler.setLevel(logging.WARNING)
    err_handler.setFormatter(fmt)
    root.addHandler(err_handler)

    # Bruit des libs
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("celery").setLevel(logging.INFO)

    _CONFIGURED = True
    logger = logging.getLogger(f"streamnews.{service}")
    logger.info(
        "Logging pret service=%s level=%s dir=%s file=%s",
        service,
        level_name,
        logs_dir(),
        log_path,
    )
    return logger


def get_logger(name: str) -> logging.Logger:
    """Logger module : preferer get_logger(__name__)."""
    if not _CONFIGURED:
        setup_logging(service=os.getenv("STREAMNEWS_ROLE", "analyzer") or "analyzer")
    return logging.getLogger(name)
