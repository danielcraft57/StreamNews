"""Schema initial StreamNews (sites, pages, articles).

Revision ID: 001
Revises:
Create Date: 2026-07-20

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _json_type():
    return sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def _json_array_default():
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return sa.text("'[]'")
    return sa.text("'[]'::jsonb")


def _json_object_default():
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return sa.text("'{}'")
    return sa.text("'{}'::jsonb")


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    json_t = _json_type()

    if not insp.has_table("sites"):
        op.create_table(
            "sites",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("url", sa.String(length=500), nullable=False),
            sa.Column("status", sa.String(length=50), server_default="pending", nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
            sa.Column("total_pages_analyzed", sa.Integer(), server_default="0", nullable=True),
            sa.Column("rss_feeds", json_t, server_default=_json_array_default(), nullable=False),
            sa.Column("celery_task_id", sa.String(length=255), nullable=True),
            sa.Column("site_title", sa.String(length=500), nullable=True),
            sa.Column("favicon_url", sa.String(length=1000), nullable=True),
            sa.Column("meta_description", sa.Text(), nullable=True),
            sa.Column("meta_extra", json_t, server_default=_json_object_default(), nullable=False),
            sa.Column("domain", sa.String(length=255), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )

    if not insp.has_table("pages"):
        op.create_table(
            "pages",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("site_id", sa.Integer(), nullable=False),
            sa.Column("url", sa.String(length=1000), nullable=False),
            sa.Column("title", sa.String(length=500), nullable=True),
            sa.Column("rss_feeds", json_t, server_default=_json_array_default(), nullable=False),
            sa.Column("analyzed_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
            sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )

    if not insp.has_table("articles"):
        op.create_table(
            "articles",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("site_id", sa.Integer(), nullable=False),
            sa.Column("feed_url", sa.String(length=1000), nullable=False),
            sa.Column("title", sa.String(length=1000), nullable=True),
            sa.Column("link", sa.String(length=2000), nullable=False),
            sa.Column("summary", sa.Text(), nullable=True),
            sa.Column("author", sa.String(length=500), nullable=True),
            sa.Column("published_at", sa.DateTime(), nullable=True),
            sa.Column("guid", sa.String(length=2000), nullable=True),
            sa.Column("dedupe_key", sa.String(length=2100), server_default="", nullable=False),
            sa.Column("fetched_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
            sa.Column("content_html", sa.Text(), nullable=True),
            sa.Column("content_text", sa.Text(), nullable=True),
            sa.Column("images", json_t, server_default=_json_array_default(), nullable=False),
            sa.Column("article_meta", json_t, server_default=_json_object_default(), nullable=False),
            sa.Column("enriched_at", sa.DateTime(), nullable=True),
            sa.Column("enrich_status", sa.String(length=50), nullable=True),
            sa.Column("enrich_error", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("site_id", "link", name="articles_site_id_link_key"),
        )

    # Index + contraintes (idempotent sur BDD existantes)
    if bind.dialect.name == "sqlite":
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_articles_site_published "
            "ON articles (site_id, published_at DESC)"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_articles_enrich_status "
            "ON articles (site_id, enrich_status)"
        )
        op.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS articles_site_id_dedupe_key_key "
            "ON articles (site_id, dedupe_key)"
        )
        op.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS sites_domain_key ON sites(domain)"
        )
    else:
        op.execute("""
            CREATE INDEX IF NOT EXISTS idx_articles_site_published
            ON articles (site_id, published_at DESC NULLS LAST)
        """)
        op.execute("""
            CREATE INDEX IF NOT EXISTS idx_articles_enrich_status
            ON articles (site_id, enrich_status)
        """)
        op.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'articles_site_id_dedupe_key_key'
                ) THEN
                    ALTER TABLE articles
                        ADD CONSTRAINT articles_site_id_dedupe_key_key
                        UNIQUE (site_id, dedupe_key);
                END IF;
            EXCEPTION WHEN others THEN NULL;
            END $$;
        """)
        op.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'sites_domain_key'
                ) THEN
                    ALTER TABLE sites ADD CONSTRAINT sites_domain_key UNIQUE (domain);
                END IF;
            EXCEPTION WHEN others THEN NULL;
            END $$;
        """)
        op.execute("""
            DO $$
            BEGIN
                ALTER TABLE pages DROP CONSTRAINT IF EXISTS pages_site_id_fkey;
                ALTER TABLE pages
                    ADD CONSTRAINT pages_site_id_fkey
                    FOREIGN KEY (site_id) REFERENCES sites(id) ON DELETE CASCADE;
                ALTER TABLE articles DROP CONSTRAINT IF EXISTS articles_site_id_fkey;
                ALTER TABLE articles
                    ADD CONSTRAINT articles_site_id_fkey
                    FOREIGN KEY (site_id) REFERENCES sites(id) ON DELETE CASCADE;
            EXCEPTION WHEN others THEN NULL;
            END $$;
        """)


def downgrade() -> None:
    op.drop_table("articles")
    op.drop_table("pages")
    op.drop_table("sites")
