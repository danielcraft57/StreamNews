"""Schema SQLAlchemy (source de verite pour Alembic)."""
from __future__ import annotations

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData()

JsonDocument = JSON().with_variant(JSONB(), "postgresql")

sites = Table(
    "sites",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("url", String(500), nullable=False),
    Column("status", String(50), nullable=False, server_default="pending"),
    Column("created_at", DateTime, server_default=func.now()),
    Column("updated_at", DateTime, server_default=func.now()),
    Column("total_pages_analyzed", Integer, server_default="0"),
    Column("rss_feeds", JsonDocument, nullable=False, server_default="[]"),
    Column("celery_task_id", String(255)),
    Column("site_title", String(500)),
    Column("favicon_url", String(1000)),
    Column("meta_description", Text),
    Column("meta_extra", JsonDocument, nullable=False, server_default="{}"),
    Column("domain", String(255)),
    UniqueConstraint("domain", name="sites_domain_key"),
)

pages = Table(
    "pages",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column(
        "site_id",
        Integer,
        ForeignKey("sites.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("url", String(1000), nullable=False),
    Column("title", String(500)),
    Column("rss_feeds", JsonDocument, nullable=False, server_default="[]"),
    Column("analyzed_at", DateTime, server_default=func.now()),
)

articles = Table(
    "articles",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column(
        "site_id",
        Integer,
        ForeignKey("sites.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("feed_url", String(1000), nullable=False),
    Column("title", String(1000)),
    Column("link", String(2000), nullable=False),
    Column("summary", Text),
    Column("author", String(500)),
    Column("published_at", DateTime),
    Column("guid", String(2000)),
    Column("dedupe_key", String(2100), nullable=False, server_default=""),
    Column("fetched_at", DateTime, server_default=func.now()),
    Column("content_html", Text),
    Column("content_text", Text),
    Column("images", JsonDocument, nullable=False, server_default="[]"),
    Column("article_meta", JsonDocument, nullable=False, server_default="{}"),
    Column("enriched_at", DateTime),
    Column("enrich_status", String(50)),
    Column("enrich_error", Text),
    UniqueConstraint("site_id", "link", name="articles_site_id_link_key"),
    UniqueConstraint("site_id", "dedupe_key", name="articles_site_id_dedupe_key_key"),
    Index("idx_articles_site_published", "site_id", "published_at"),
    Index("idx_articles_enrich_status", "site_id", "enrich_status"),
)
