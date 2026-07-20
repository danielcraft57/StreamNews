"""Entites normalisees (contrats Pydantic pour tables relationnelles)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class RssFeedRecord(BaseModel):
    id: Optional[int] = None
    site_id: int
    url: str
    title: str = "Flux RSS"
    feed_type: str = "detected"
    source_page_id: Optional[int] = None
    created_at: Optional[datetime] = None


class ArticleImageRecord(BaseModel):
    id: Optional[int] = None
    article_id: int
    url: str
    alt: Optional[str] = None
    source: Optional[str] = None
    is_primary: bool = False
    sort_order: int = 0


class ArticleKeywordRecord(BaseModel):
    id: Optional[int] = None
    article_id: int
    keyword: str
    source: str = "unknown"


class ArticleAnalysisRecord(BaseModel):
    id: Optional[int] = None
    article_id: int
    tool_name: str
    status: str
    result: Dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None
    analyzed_at: Optional[datetime] = None


class ArticleMetaNormRecord(BaseModel):
    article_id: int
    canonical_url: Optional[str] = None
    date_published: Optional[datetime] = None
    schema_type: Optional[str] = None
    reading_time_minutes: Optional[int] = None
    primary_image_url: Optional[str] = None
    domain: Optional[str] = None
    extra: Dict[str, Any] = Field(default_factory=dict)


class ArticleRecord(BaseModel):
    """Article + relations normalisees (contrat lecture API/services)."""

    id: int
    site_id: int
    feed_id: Optional[int] = None
    feed_url: str = ""
    title: Optional[str] = None
    link: str
    summary: Optional[str] = None
    author: Optional[str] = None
    published_at: Optional[datetime] = None
    guid: Optional[str] = None
    content_html: Optional[str] = None
    content_text: Optional[str] = None
    enrich_status: Optional[str] = None
    enrich_error: Optional[str] = None
    enriched_at: Optional[datetime] = None
    analysis_status: Optional[str] = None
    analysis_error: Optional[str] = None
    analyzed_at: Optional[datetime] = None
    fetched_at: Optional[datetime] = None
    images: List[ArticleImageRecord] = Field(default_factory=list)
    keywords: List[ArticleKeywordRecord] = Field(default_factory=list)
    analyses: List[ArticleAnalysisRecord] = Field(default_factory=list)
    meta_norm: Optional[ArticleMetaNormRecord] = None

    def to_api_dict(self) -> Dict[str, Any]:
        """Shape attendu par le front / FastAPI (images + article_meta)."""
        from repositories.normalized_read import rebuild_article_meta

        meta = rebuild_article_meta(
            meta_norm=self.meta_norm.model_dump() if self.meta_norm else None,
            keywords=[k.model_dump() for k in self.keywords],
            analyses={
                a.tool_name: {
                    **(a.result or {}),
                    "status": a.status,
                    **({"error": a.error_message} if a.error_message else {}),
                    **(
                        {"analyzed_at": a.analyzed_at.isoformat()}
                        if a.analyzed_at
                        else {}
                    ),
                }
                for a in self.analyses
            },
            analysis_status=self.analysis_status,
            analysis_error=self.analysis_error,
            analyzed_at=self.analyzed_at,
            legacy_meta={},
        )
        data = {
            "id": self.id,
            "site_id": self.site_id,
            "feed_id": self.feed_id,
            "feed_url": self.feed_url,
            "title": self.title,
            "link": self.link,
            "summary": self.summary,
            "author": self.author,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "guid": self.guid,
            "content_html": self.content_html,
            "content_text": self.content_text,
            "enrich_status": self.enrich_status,
            "enrich_error": self.enrich_error,
            "enriched_at": self.enriched_at.isoformat() if self.enriched_at else None,
            "analysis_status": self.analysis_status,
            "analysis_error": self.analysis_error,
            "analyzed_at": self.analyzed_at.isoformat() if self.analyzed_at else None,
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
            "images": [
                {
                    "url": img.url,
                    "alt": img.alt or "",
                    "source": img.source or "legacy",
                    "is_primary": img.is_primary,
                }
                for img in self.images
            ],
            "article_meta": meta,
        }
        return data


class SiteRecord(BaseModel):
    id: int
    url: str
    status: str = "pending"
    domain: Optional[str] = None
    site_title: Optional[str] = None
    favicon_url: Optional[str] = None
    meta_description: Optional[str] = None
    meta_extra: Dict[str, Any] = Field(default_factory=dict)
    total_pages_analyzed: int = 0
    celery_task_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    rss_feeds: List[RssFeedRecord] = Field(default_factory=list)

    def to_api_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "url": self.url,
            "status": self.status,
            "domain": self.domain,
            "site_title": self.site_title,
            "favicon_url": self.favicon_url,
            "meta_description": self.meta_description,
            "meta_extra": self.meta_extra,
            "total_pages_analyzed": self.total_pages_analyzed,
            "celery_task_id": self.celery_task_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "rss_feeds": [
                {
                    "url": f.url,
                    "title": f.title,
                    "type": f.feed_type,
                    "source_page_id": f.source_page_id,
                }
                for f in self.rss_feeds
            ],
        }
