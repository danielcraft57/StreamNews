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
    """Vue article avec relations normalisees (lecture cible Phase 3)."""

    id: int
    site_id: int
    feed_id: Optional[int] = None
    feed_url: str
    title: Optional[str] = None
    link: str
    summary: Optional[str] = None
    author: Optional[str] = None
    published_at: Optional[datetime] = None
    guid: Optional[str] = None
    content_html: Optional[str] = None
    content_text: Optional[str] = None
    enrich_status: Optional[str] = None
    analysis_status: Optional[str] = None
    analysis_error: Optional[str] = None
    analyzed_at: Optional[datetime] = None
    images: List[ArticleImageRecord] = Field(default_factory=list)
    keywords: List[ArticleKeywordRecord] = Field(default_factory=list)
    analyses: List[ArticleAnalysisRecord] = Field(default_factory=list)
    meta_norm: Optional[ArticleMetaNormRecord] = None
    # Legacy JSON (dual-read Phase 2-3)
    article_meta: Dict[str, Any] = Field(default_factory=dict)
