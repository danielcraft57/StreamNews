"""Tables normalisees : rss_feeds, article_images, keywords, analyses, meta.

Revision ID: 002
Revises: 001
Create Date: 2026-07-20

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from schema_migrate_helpers import (
    cleanup_sqlite_alembic_temp_tables,
    ensure_article_extension_columns,
    ensure_article_indexes,
)

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _json_type():
    return sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def _json_object_default():
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return sa.text("'{}'")
    return sa.text("'{}'::jsonb")


def _article_columns(insp) -> set[str]:
    if not insp.has_table("articles"):
        return set()
    return {c["name"] for c in insp.get_columns("articles")}


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    json_t = _json_type()
    is_sqlite = bind.dialect.name == "sqlite"

    if not insp.has_table("pages"):
        return

    cleanup_sqlite_alembic_temp_tables()

    # UNIQUE pages(site_id, url) si absent
    if is_sqlite:
        op.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS pages_site_id_url_key "
            "ON pages (site_id, url)"
        )
    else:
        op.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'pages_site_id_url_key'
                ) THEN
                    ALTER TABLE pages
                        ADD CONSTRAINT pages_site_id_url_key UNIQUE (site_id, url);
                END IF;
            EXCEPTION WHEN others THEN NULL;
            END $$;
        """)

    if not insp.has_table("rss_feeds"):
        op.create_table(
            "rss_feeds",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("site_id", sa.Integer(), nullable=False),
            sa.Column("url", sa.String(length=1000), nullable=False),
            sa.Column("title", sa.String(length=500), server_default="Flux RSS", nullable=False),
            sa.Column("feed_type", sa.String(length=50), server_default="detected", nullable=False),
            sa.Column("source_page_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
            sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["source_page_id"], ["pages.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("site_id", "url", name="rss_feeds_site_id_url_key"),
        )
        op.create_index("idx_rss_feeds_site", "rss_feeds", ["site_id"])

    ensure_article_extension_columns(is_sqlite)
    ensure_article_indexes(is_sqlite)

    insp = sa.inspect(bind)
    if not insp.has_table("article_images"):
        op.create_table(
            "article_images",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("article_id", sa.Integer(), nullable=False),
            sa.Column("url", sa.String(length=2000), nullable=False),
            sa.Column("alt", sa.String(length=500), nullable=True),
            sa.Column("source", sa.String(length=50), nullable=True),
            sa.Column("is_primary", sa.Boolean(), server_default=sa.text("0"), nullable=False),
            sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
            sa.ForeignKeyConstraint(["article_id"], ["articles.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("article_id", "url", name="article_images_article_id_url_key"),
        )
        op.create_index("idx_article_images_article", "article_images", ["article_id"])

    if not insp.has_table("article_keywords"):
        op.create_table(
            "article_keywords",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("article_id", sa.Integer(), nullable=False),
            sa.Column("keyword", sa.String(length=500), nullable=False),
            sa.Column("source", sa.String(length=50), server_default="unknown", nullable=False),
            sa.ForeignKeyConstraint(["article_id"], ["articles.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "article_id", "keyword", "source", name="article_keywords_article_keyword_source_key"
            ),
        )
        op.create_index("idx_article_keywords_article", "article_keywords", ["article_id"])

    if not insp.has_table("article_analyses"):
        op.create_table(
            "article_analyses",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("article_id", sa.Integer(), nullable=False),
            sa.Column("tool_name", sa.String(length=100), nullable=False),
            sa.Column("status", sa.String(length=50), nullable=False),
            sa.Column("result", json_t, server_default=_json_object_default(), nullable=False),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("analyzed_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["article_id"], ["articles.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("article_id", "tool_name", name="article_analyses_article_tool_key"),
        )
        op.create_index("idx_article_analyses_article", "article_analyses", ["article_id"])

    if not insp.has_table("article_meta_norm"):
        op.create_table(
            "article_meta_norm",
            sa.Column("article_id", sa.Integer(), nullable=False),
            sa.Column("canonical_url", sa.String(length=2000), nullable=True),
            sa.Column("date_published", sa.DateTime(), nullable=True),
            sa.Column("schema_type", sa.String(length=100), nullable=True),
            sa.Column("reading_time_minutes", sa.Integer(), nullable=True),
            sa.Column("primary_image_url", sa.String(length=2000), nullable=True),
            sa.Column("domain", sa.String(length=255), nullable=True),
            sa.Column("extra", json_t, server_default=_json_object_default(), nullable=False),
            sa.ForeignKeyConstraint(["article_id"], ["articles.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("article_id"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    cleanup_sqlite_alembic_temp_tables()

    for table in (
        "article_meta_norm",
        "article_analyses",
        "article_keywords",
        "article_images",
    ):
        if is_sqlite:
            op.execute(f"DROP TABLE IF EXISTS {table}")
        elif sa.inspect(bind).has_table(table):
            op.drop_table(table)

    if not is_sqlite:
        cols = _article_columns(sa.inspect(bind))
        for col in ("analyzed_at", "analysis_error", "analysis_status", "feed_id"):
            if col in cols:
                op.drop_column("articles", col)

    if sa.inspect(bind).has_table("rss_feeds"):
        if is_sqlite:
            op.execute("DROP INDEX IF EXISTS idx_rss_feeds_site")
            op.execute("DROP TABLE IF EXISTS rss_feeds")
        else:
            op.drop_index("idx_rss_feeds_site", table_name="rss_feeds")
            op.drop_table("rss_feeds")
