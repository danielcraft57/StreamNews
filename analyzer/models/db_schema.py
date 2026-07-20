"""Schema SQLAlchemy (source de verite pour Alembic)."""
from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
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
    Column("analyzed_at", DateTime, server_default=func.now()),
    UniqueConstraint("site_id", "url", name="pages_site_id_url_key"),
)

rss_feeds = Table(
    "rss_feeds",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column(
        "site_id",
        Integer,
        ForeignKey("sites.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("url", String(1000), nullable=False),
    Column("title", String(500), nullable=False, server_default="Flux RSS"),
    Column("feed_type", String(50), nullable=False, server_default="detected"),
    Column(
        "source_page_id",
        Integer,
        ForeignKey("pages.id", ondelete="SET NULL"),
    ),
    Column("created_at", DateTime, server_default=func.now()),
    UniqueConstraint("site_id", "url", name="rss_feeds_site_id_url_key"),
    Index("idx_rss_feeds_site", "site_id"),
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
    Column(
        "feed_id",
        Integer,
        ForeignKey("rss_feeds.id", ondelete="SET NULL"),
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
    Column("enriched_at", DateTime),
    Column("enrich_status", String(50)),
    Column("enrich_error", Text),
    Column("analysis_status", String(50)),
    Column("analysis_error", Text),
    Column("analyzed_at", DateTime),
    UniqueConstraint("site_id", "link", name="articles_site_id_link_key"),
    UniqueConstraint("site_id", "dedupe_key", name="articles_site_id_dedupe_key_key"),
    Index("idx_articles_site_published", "site_id", "published_at"),
    Index("idx_articles_enrich_status", "site_id", "enrich_status"),
    Index("idx_articles_analysis_status", "site_id", "analysis_status"),
    Index("idx_articles_feed", "feed_id"),
)

article_media = Table(
    "article_media",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column(
        "article_id",
        Integer,
        ForeignKey("articles.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("media_type", String(20), nullable=False, server_default="image"),
    Column("url", String(2000), nullable=False),
    Column("mime_type", String(100)),
    Column("title", String(500)),
    Column("alt", String(500)),
    Column("source", String(50)),
    Column("thumbnail_url", String(2000)),
    Column("duration_ms", Integer),
    Column("width", Integer),
    Column("height", Integer),
    Column("is_primary", Boolean, nullable=False, server_default="0"),
    Column("sort_order", Integer, nullable=False, server_default="0"),
    Column("extra", JsonDocument, nullable=False, server_default="{}"),
    Index("idx_article_media_article", "article_id"),
    Index("idx_article_media_article_type", "article_id", "media_type"),
    UniqueConstraint("article_id", "url", name="article_media_article_id_url_key"),
)

persons = Table(
    "persons",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("display_name", String(500)),
    Column("created_at", DateTime, server_default=func.now()),
    Column("meta", JsonDocument, nullable=False, server_default="{}"),
    Index("idx_persons_display_name", "display_name"),
)

article_entities = Table(
    "article_entities",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column(
        "article_id",
        Integer,
        ForeignKey("articles.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("text", String(500), nullable=False),
    Column("label", String(100), nullable=False),
    Column("start_char", Integer),
    Column("end_char", Integer),
    Column("source", String(50), nullable=False, server_default="ner_spacy"),
    Column(
        "person_id",
        Integer,
        ForeignKey("persons.id", ondelete="SET NULL"),
    ),
    Column(
        "media_id",
        Integer,
        ForeignKey("article_media.id", ondelete="SET NULL"),
    ),
    UniqueConstraint(
        "article_id",
        "text",
        "label",
        "source",
        name="article_entities_article_text_label_source_key",
    ),
    Index("idx_article_entities_article", "article_id"),
    Index("idx_article_entities_person", "person_id"),
    Index("idx_article_entities_media", "media_id"),
)

article_faces = Table(
    "article_faces",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column(
        "article_id",
        Integer,
        ForeignKey("articles.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "media_id",
        Integer,
        ForeignKey("article_media.id", ondelete="SET NULL"),
    ),
    Column(
        "person_id",
        Integer,
        ForeignKey("persons.id", ondelete="SET NULL"),
    ),
    Column("bbox_x", Float),
    Column("bbox_y", Float),
    Column("bbox_w", Float),
    Column("bbox_h", Float),
    Column("bbox_unit", String(20), nullable=False, server_default="ratio"),
    Column("confidence", Float),
    Column("embedding", LargeBinary),
    Column("embedding_dim", Integer),
    Column("tool_name", String(100), nullable=False, server_default="face_detect"),
    Column("detected_at", DateTime),
    Index("idx_article_faces_article", "article_id"),
    Index("idx_article_faces_media", "media_id"),
    Index("idx_article_faces_person", "person_id"),
)

article_keywords = Table(
    "article_keywords",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column(
        "article_id",
        Integer,
        ForeignKey("articles.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("keyword", String(500), nullable=False),
    Column("source", String(50), nullable=False, server_default="unknown"),
    UniqueConstraint(
        "article_id",
        "keyword",
        "source",
        name="article_keywords_article_keyword_source_key",
    ),
    Index("idx_article_keywords_article", "article_id"),
)

article_analyses = Table(
    "article_analyses",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column(
        "article_id",
        Integer,
        ForeignKey("articles.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("tool_name", String(100), nullable=False),
    Column("status", String(50), nullable=False),
    Column("result", JsonDocument, nullable=False, server_default="{}"),
    Column("error_message", Text),
    Column("analyzed_at", DateTime),
    UniqueConstraint("article_id", "tool_name", name="article_analyses_article_tool_key"),
    Index("idx_article_analyses_article", "article_id"),
)

article_meta_norm = Table(
    "article_meta_norm",
    metadata,
    Column(
        "article_id",
        Integer,
        ForeignKey("articles.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("canonical_url", String(2000)),
    Column("date_published", DateTime),
    Column("schema_type", String(100)),
    Column("reading_time_minutes", Integer),
    Column("primary_image_url", String(2000)),
    Column("domain", String(255)),
    Column("extra", JsonDocument, nullable=False, server_default="{}"),
)
