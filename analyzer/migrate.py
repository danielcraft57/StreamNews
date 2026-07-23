"""Executer les migrations Alembic (SQLite local + Postgres prod)."""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import unquote

from alembic import command
from alembic.config import Config

_ANALYZER_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _ANALYZER_DIR.parent

# Cle stable pour serialiser les upgrades concurrentes (flotte parallele).
_PG_MIGRATION_LOCK_KEY = 872_014_305


def _sync_database_url(url: str) -> str:
    """URL SQLAlchemy synchrone pour Alembic."""
    if url.startswith("sqlite+aiosqlite:"):
        return _sync_database_url("sqlite:" + url.split(":", 1)[1])
    if url.startswith("postgresql+asyncpg:"):
        return "postgresql+psycopg2:" + url.split(":", 1)[1]
    if url.startswith("sqlite:///./") or (
        url.startswith("sqlite:///") and not url.startswith("sqlite:////")
    ):
        raw = url.replace("sqlite:///", "", 1).split("?")[0]
        path = Path(unquote(raw))
        if not path.is_absolute():
            path = (_REPO_ROOT / path).resolve()
        else:
            path = path.resolve()
        return f"sqlite:///{path.as_posix()}"
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


@contextmanager
def _postgres_migration_lock(url: str):
    """Serialise alembic entre noeuds (deploy-fleet parallele + init_db au boot).

    Lock session-level en AUTOCOMMIT : survit aux commit Alembic sur d'autres connexions.
    """
    if not url.startswith("postgresql"):
        yield
        return
    import sqlalchemy as sa

    engine = sa.create_engine(url)
    conn = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    try:
        conn.execute(sa.text("SELECT pg_advisory_lock(:k)"), {"k": _PG_MIGRATION_LOCK_KEY})
        try:
            yield
        finally:
            conn.execute(sa.text("SELECT pg_advisory_unlock(:k)"), {"k": _PG_MIGRATION_LOCK_KEY})
    finally:
        conn.close()
        engine.dispose()


def run_migrations(database_url: str | None = None, *, reset: bool = False) -> str:
    """Applique les migrations. reset=True : downgrade base puis upgrade head."""
    url = _sync_database_url(database_url or os.getenv("DATABASE_URL", "sqlite:///./data/streamnews.db"))
    _ensure_sqlite_parent(url)
    cfg = alembic_config(url)
    cfg.set_main_option("sqlalchemy.url", url)
    with _postgres_migration_lock(url):
        if reset:
            # SQLite neuf : pas de downgrade (fichier absent).
            # Postgres / SQLite existant : recreate complete.
            if url.startswith("sqlite:") and not _sqlite_db_exists(url):
                pass
            else:
                command.downgrade(cfg, "base")
        command.upgrade(cfg, "head")
    _repair_schema_after_upgrade(url)
    return "head"


def _repair_schema_after_upgrade(url: str) -> None:
    """Securite : colonnes articles manquantes apres upgrade (BDD partielles)."""
    if not url.startswith("sqlite:"):
        return
    import sqlalchemy as sa
    from schema_migrate_helpers import article_columns

    engine = sa.create_engine(url)
    with engine.begin() as conn:
        conn.execute(sa.text("DROP TABLE IF EXISTS _alembic_tmp_articles"))
        cols = article_columns(sa.inspect(conn))
        needed = {"feed_id", "analysis_status", "analysis_error", "analyzed_at"}
        if needed.issubset(cols):
            return
        if "feed_id" not in cols:
            conn.execute(sa.text("ALTER TABLE articles ADD COLUMN feed_id INTEGER"))
        cols = {c["name"] for c in sa.inspect(conn).get_columns("articles")}
        if "analysis_status" not in cols:
            conn.execute(sa.text("ALTER TABLE articles ADD COLUMN analysis_status VARCHAR(50)"))
            conn.execute(sa.text("ALTER TABLE articles ADD COLUMN analysis_error TEXT"))
            conn.execute(sa.text("ALTER TABLE articles ADD COLUMN analyzed_at DATETIME"))
        conn.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_articles_feed ON articles (feed_id)"))
        conn.execute(
            sa.text(
                "CREATE INDEX IF NOT EXISTS idx_articles_analysis_status "
                "ON articles (site_id, analysis_status)"
            )
        )
    engine.dispose()


def stamp_head(database_url: str | None = None) -> None:
    """Marque la BDD existante comme a jour (sans executer les CREATE)."""
    command.stamp(alembic_config(database_url), "head")
