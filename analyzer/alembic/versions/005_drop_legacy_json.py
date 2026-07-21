"""Drop colonnes JSON legacy + indexes lecture (Phase 4).

Revision ID: 005
Revises: 004
Create Date: 2026-07-20

Source de verite = tables normalisees (rss_feeds, article_images,
article_keywords, article_analyses, article_meta_norm).
Conserve sites.meta_extra (petit), article_analyses.result,
article_meta_norm.extra.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _cols(insp, table: str) -> set[str]:
    if not insp.has_table(table):
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def _drop_column(table: str, column: str, *, is_sqlite: bool) -> None:
    insp = sa.inspect(op.get_bind())
    if column not in _cols(insp, table):
        return
    if is_sqlite:
        with op.batch_alter_table(table) as batch:
            batch.drop_column(column)
    else:
        op.drop_column(table, column)


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    _drop_column("sites", "rss_feeds", is_sqlite=is_sqlite)
    _drop_column("pages", "rss_feeds", is_sqlite=is_sqlite)
    _drop_column("articles", "images", is_sqlite=is_sqlite)
    _drop_column("articles", "article_meta", is_sqlite=is_sqlite)

    # Indexes lecture (hot paths get_site_articles / hydrate / needing_analysis)
    if is_sqlite:
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_article_images_article_sort "
            "ON article_images (article_id, sort_order)"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_articles_needing_analysis "
            "ON articles (site_id, enrich_status, analysis_status)"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_rss_feeds_site_url "
            "ON rss_feeds (site_id, url)"
        )
        op.execute("ANALYZE")
    else:
        op.execute("""
            CREATE INDEX IF NOT EXISTS idx_article_images_article_sort
            ON article_images (article_id, sort_order)
        """)
        op.execute("""
            CREATE INDEX IF NOT EXISTS idx_articles_needing_analysis
            ON articles (site_id, enrich_status, analysis_status)
            WHERE enrich_status = 'ok'
              AND (analysis_status IS NULL OR analysis_status NOT IN ('ok', 'pending'))
        """)
        op.execute("""
            CREATE INDEX IF NOT EXISTS idx_rss_feeds_site_url
            ON rss_feeds (site_id, url)
        """)
        # Covering index Postgres pour liste articles (evite heap lookup)
        op.execute("""
            CREATE INDEX IF NOT EXISTS idx_articles_site_list_cover
            ON articles (site_id, published_at DESC NULLS LAST)
            INCLUDE (title, link, enrich_status, analysis_status, feed_id, fetched_at)
        """)
        op.execute("ANALYZE articles")
        op.execute("ANALYZE article_images")
        op.execute("ANALYZE rss_feeds")


def downgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    json_t = sa.JSON()
    default_arr = sa.text("'[]'") if is_sqlite else sa.text("'[]'::jsonb")
    default_obj = sa.text("'{}'") if is_sqlite else sa.text("'{}'::jsonb")

    insp = sa.inspect(bind)
    if "rss_feeds" not in _cols(insp, "sites"):
        op.add_column(
            "sites",
            sa.Column("rss_feeds", json_t, server_default=default_arr, nullable=False),
        )
    if "rss_feeds" not in _cols(insp, "pages"):
        op.add_column(
            "pages",
            sa.Column("rss_feeds", json_t, server_default=default_arr, nullable=False),
        )
    if "images" not in _cols(insp, "articles"):
        op.add_column(
            "articles",
            sa.Column("images", json_t, server_default=default_arr, nullable=False),
        )
    if "article_meta" not in _cols(insp, "articles"):
        op.add_column(
            "articles",
            sa.Column("article_meta", json_t, server_default=default_obj, nullable=False),
        )
