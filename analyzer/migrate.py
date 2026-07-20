"""Executer les migrations Alembic (SQLite local + Postgres prod)."""
from __future__ import annotations

import os
from pathlib import Path

from alembic import command
from alembic.config import Config

_ANALYZER_DIR = Path(__file__).resolve().parent


def _sync_database_url(url: str) -> str:
    """URL SQLAlchemy synchrone pour Alembic."""
    if url.startswith("sqlite+aiosqlite:"):
        return "sqlite:" + url.split(":", 1)[1]
    if url.startswith("postgresql+asyncpg:"):
        return "postgresql+psycopg2:" + url.split(":", 1)[1]
    if url.startswith("sqlite:///./"):
        rel = url.replace("sqlite:///", "", 1).split("?")[0]
        abs_path = (_ANALYZER_DIR / rel).resolve()
        return f"sqlite:///{abs_path.as_posix()}"
    return url


def _ensure_sqlite_parent(url: str) -> None:
    if not url.startswith("sqlite:"):
        return
    raw = url.replace("sqlite:///", "", 1).split("?")[0]
    if raw == ":memory:" or not raw:
        return
    Path(raw).parent.mkdir(parents=True, exist_ok=True)


def _sqlite_db_exists(url: str) -> bool:
    if not url.startswith("sqlite:"):
        return True
    raw = url.replace("sqlite:///", "", 1).split("?")[0]
    return raw != ":memory:" and Path(raw).is_file()


def alembic_config(database_url: str | None = None) -> Config:
    cfg = Config(str(_ANALYZER_DIR / "alembic.ini"))
    url = _sync_database_url(database_url or os.getenv("DATABASE_URL", "sqlite:///./data/streamnews.db"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.set_main_option("script_location", str(_ANALYZER_DIR / "alembic"))
    return cfg


def run_migrations(database_url: str | None = None, *, reset: bool = False) -> str:
    """Applique les migrations. reset=True : downgrade base puis upgrade head."""
    url = _sync_database_url(database_url or os.getenv("DATABASE_URL", "sqlite:///./data/streamnews.db"))
    _ensure_sqlite_parent(url)
    cfg = alembic_config(url)
    cfg.set_main_option("sqlalchemy.url", url)
    if reset and _sqlite_db_exists(url):
        command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    return "head"


def stamp_head(database_url: str | None = None) -> None:
    """Marque la BDD existante comme a jour (sans executer les CREATE)."""
    command.stamp(alembic_config(database_url), "head")
