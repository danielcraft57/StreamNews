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


class ArticleMediaRecord(BaseModel):
    id: Optional[int] = None
    article_id: int
    media_type: str = "image"  # image | video | audio
    url: str
    mime_type: Optional[str] = None
    title: Optional[str] = None
    alt: Optional[str] = None
    source: Optional[str] = None
    thumbnail_url: Optional[str] = None
    duration_ms: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    is_primary: bool = False
    sort_order: int = 0
    extra: Dict[str, Any] = Field(default_factory=dict)


# Alias compat
class ArticleImageRecord(ArticleMediaRecord):
    media_type: str = "image"


class ArticleKeywordRecord(BaseModel):
    id: Optional[int] = None
    article_id: int
    keyword: str
    source: str = "unknown"


class ArticleEntityRecord(BaseModel):
    id: Optional[int] = None
    article_id: int
    text: str
    label: str
    start_char: Optional[int] = None
    end_char: Optional[int] = None
    source: str = "ner_spacy"
    person_id: Optional[int] = None
    media_id: Optional[int] = None


class PersonRecord(BaseModel):
    id: Optional[int] = None
    display_name: Optional[str] = None
    created_at: Optional[datetime] = None
    meta: Dict[str, Any] = Field(default_factory=dict)


class ArticleFaceRecord(BaseModel):
    id: Optional[int] = None
    article_id: int
    media_id: Optional[int] = None
    person_id: Optional[int] = None
    bbox_x: Optional[float] = None
    bbox_y: Optional[float] = None
    bbox_w: Optional[float] = None
    bbox_h: Optional[float] = None
    bbox_unit: str = "ratio"
    confidence: Optional[float] = None
    embedding_dim: Optional[int] = None
    tool_name: str = "face_detect"
    detected_at: Optional[datetime] = None


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


def _media_api(m: ArticleMediaRecord) -> Dict[str, Any]:
    return {
        "id": m.id,
        "media_type": m.media_type,
        "url": m.url,
        "mime_type": m.mime_type,
        "title": m.title,
        "alt": m.alt or "",
        "source": m.source or "legacy",
        "thumbnail_url": m.thumbnail_url,
        "duration_ms": m.duration_ms,
        "width": m.width,
        "height": m.height,
        "is_primary": m.is_primary,
        "sort_order": m.sort_order,
    }


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
    media: List[ArticleMediaRecord] = Field(default_factory=list)
    images: List[ArticleMediaRecord] = Field(default_factory=list)
    keywords: List[ArticleKeywordRecord] = Field(default_factory=list)
    entities: List[ArticleEntityRecord] = Field(default_factory=list)
    faces: List[ArticleFaceRecord] = Field(default_factory=list)
    analyses: List[ArticleAnalysisRecord] = Field(default_factory=list)
    meta_norm: Optional[ArticleMetaNormRecord] = None

    def to_api_dict(self) -> Dict[str, Any]:
        """Shape attendu par le front / FastAPI."""
        from repositories.normalized_read import rebuild_article_meta

        media = self.media or self.images
        images = [m for m in media if m.media_type == "image"]
        videos = [m for m in media if m.media_type == "video"]
        audios = [m for m in media if m.media_type == "audio"]

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
        if self.entities:
            meta["entities"] = [
                {"text": e.text, "label": e.label, "source": e.source}
                for e in self.entities
            ]
        if self.faces:
            meta["faces_count"] = len(self.faces)

        return {
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
            "images": [_media_api(m) for m in images],
            "videos": [_media_api(m) for m in videos],
            "audios": [_media_api(m) for m in audios],
            "media": [_media_api(m) for m in media],
            "entities": [
                {
                    "text": e.text,
                    "label": e.label,
                    "start_char": e.start_char,
                    "end_char": e.end_char,
                    "source": e.source,
                    "person_id": e.person_id,
                    "media_id": e.media_id,
                }
                for e in self.entities
            ],
            "faces": [
                {
                    "id": f.id,
                    "media_id": f.media_id,
                    "person_id": f.person_id,
                    "bbox": {
                        "x": f.bbox_x,
                        "y": f.bbox_y,
                        "w": f.bbox_w,
                        "h": f.bbox_h,
                        "unit": f.bbox_unit,
                    },
                    "confidence": f.confidence,
                    "tool_name": f.tool_name,
                }
                for f in self.faces
            ],
            "article_meta": meta,
        }


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
