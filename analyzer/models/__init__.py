"""Domain models (Pydantic) - contrats stables entre services / API / tasks."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from models.entities import (
    ArticleAnalysisRecord,
    ArticleEntityRecord,
    ArticleFaceRecord,
    ArticleImageRecord,
    ArticleKeywordRecord,
    ArticleMediaRecord,
    ArticleMetaNormRecord,
    ArticleRecord,
    PersonRecord,
    RssFeedRecord,
    SiteRecord,
)


class FeedRef(BaseModel):
    url: str
    title: str = "Flux RSS"
    type: str = "detected"
    source_page: Optional[str] = None


class PageSnapshot(BaseModel):
    url: str
    title: Optional[str] = None
    rss_feeds: List[FeedRef] = Field(default_factory=list)


class ArticleCandidate(BaseModel):
    feed_url: str
    title: str = "Sans titre"
    link: str
    summary: Optional[str] = None
    author: Optional[str] = None
    published_at: Optional[datetime] = None
    guid: Optional[str] = None
    images: List[Dict[str, Any]] = Field(default_factory=list)
    videos: List[Dict[str, Any]] = Field(default_factory=list)
    audios: List[Dict[str, Any]] = Field(default_factory=list)
    article_meta: Dict[str, Any] = Field(default_factory=dict)


class CrawlResult(BaseModel):
    status: str = "completed"
    rss_feeds: List[FeedRef] = Field(default_factory=list)
    total_pages_analyzed: int = 0
    error: Optional[str] = None
    site_meta: Optional[dict] = None


class IngestFeedResult(BaseModel):
    feed_url: str
    articles_upserted: int = 0
    ok: bool = True
    error: Optional[str] = None


class PipelineSummary(BaseModel):
    site_id: int
    url: str
    status: str
    rss_count: int = 0
    articles_count: int = 0
    pages_analyzed: int = 0


__all__ = [
    "FeedRef",
    "PageSnapshot",
    "ArticleCandidate",
    "CrawlResult",
    "IngestFeedResult",
    "PipelineSummary",
    "RssFeedRecord",
    "ArticleImageRecord",
    "ArticleMediaRecord",
    "ArticleKeywordRecord",
    "ArticleEntityRecord",
    "ArticleFaceRecord",
    "PersonRecord",
    "ArticleAnalysisRecord",
    "ArticleMetaNormRecord",
    "ArticleRecord",
    "SiteRecord",
]
