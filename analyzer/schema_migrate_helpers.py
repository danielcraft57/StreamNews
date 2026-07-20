"""Helpers partages entre migrations Alembic."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


def article_columns(insp) -> set[str]:
    if not insp.has_table("articles"):
        return set()
    return {c["name"] for c in insp.get_columns("articles")}


def _sqlite_add_column(name: str, sql_type: str) -> None:
    try:
        op.execute(f"ALTER TABLE articles ADD COLUMN {name} {sql_type}")
    except Exception as exc:
        if "duplicate column" not in str(exc).lower():
            raise


def ensure_article_extension_columns(is_sqlite: bool) -> None:
    bind = op.get_bind()
    cols = article_columns(sa.inspect(bind))
    if is_sqlite:
        if "feed_id" not in cols:
            _sqlite_add_column("feed_id", "INTEGER")
        if "analysis_status" not in cols:
            _sqlite_add_column("analysis_status", "VARCHAR(50)")
            _sqlite_add_column("analysis_error", "TEXT")
            _sqlite_add_column("analyzed_at", "DATETIME")
        return

    if "feed_id" not in cols:
        op.add_column("articles", sa.Column("feed_id", sa.Integer(), nullable=True))
    if "analysis_status" not in cols:
        op.execute("ALTER TABLE articles ADD COLUMN IF NOT EXISTS analysis_status VARCHAR(50)")
        op.execute("ALTER TABLE articles ADD COLUMN IF NOT EXISTS analysis_error TEXT")
        op.execute("ALTER TABLE articles ADD COLUMN IF NOT EXISTS analyzed_at TIMESTAMP")


def ensure_article_indexes(is_sqlite: bool) -> None:
    cols = article_columns(sa.inspect(op.get_bind()))
    if "feed_id" in cols:
        op.execute("CREATE INDEX IF NOT EXISTS idx_articles_feed ON articles (feed_id)")
    if "analysis_status" in cols:
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_articles_analysis_status "
            "ON articles (site_id, analysis_status)"
        )
    if not is_sqlite and "feed_id" in cols:
        op.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'articles_feed_id_fkey'
                ) THEN
                    ALTER TABLE articles
                        ADD CONSTRAINT articles_feed_id_fkey
                        FOREIGN KEY (feed_id) REFERENCES rss_feeds(id) ON DELETE SET NULL;
                END IF;
            EXCEPTION WHEN others THEN NULL;
            END $$;
        """)


def cleanup_sqlite_alembic_temp_tables() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return
    op.execute("DROP TABLE IF EXISTS _alembic_tmp_articles")
    op.execute("DROP TABLE IF EXISTS _alembic_tmp_pages")
    op.execute("DROP TABLE IF EXISTS _alembic_tmp_sites")
