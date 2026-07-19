"""Service d'ingestion RSS : parse un flux -> articles (CPU/IO isole)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from time import mktime
from typing import List, Optional

import feedparser

from logging_config import get_logger
from models import ArticleCandidate, IngestFeedResult
from utils import normalize_identifier, normalize_url

logger = get_logger(__name__)


class IngestService:
    def __init__(self, max_entries: int = 50, summary_max_len: int = 4000):
        self.max_entries = max_entries
        self.summary_max_len = summary_max_len

    def parse_feed(self, feed_url: str) -> List[ArticleCandidate]:
        """Parse synchrone (feedparser) - a lancer dans un worker Celery."""
        articles: List[ArticleCandidate] = []
        try:
            parsed = feedparser.parse(feed_url)
        except Exception as exc:
            logger.warning("parse_feed failed %s: %s", feed_url, exc)
            return articles

        for entry in (parsed.entries or [])[: self.max_entries]:
            link = normalize_url(entry.get("link") or entry.get("id") or "")
            if not link:
                continue

            published_at = None
            published_parsed = entry.get("published_parsed") or entry.get("updated_parsed")
            if published_parsed:
                try:
                    published_at = datetime.fromtimestamp(
                        mktime(published_parsed), tz=timezone.utc
                    ).replace(tzinfo=None)
                except (OverflowError, ValueError, TypeError):
                    published_at = None

            summary = entry.get("summary") or entry.get("description") or ""
            if len(summary) > self.summary_max_len:
                summary = summary[: self.summary_max_len] + "…"

            articles.append(
                ArticleCandidate(
                    feed_url=normalize_url(feed_url) or feed_url,
                    title=entry.get("title") or "Sans titre",
                    link=link,
                    summary=summary or None,
                    author=entry.get("author"),
                    published_at=published_at,
                    guid=normalize_identifier(entry.get("id") or entry.get("guid")),
                )
            )
        return articles

    def result(self, feed_url: str, articles: List[ArticleCandidate], error: Optional[str] = None) -> IngestFeedResult:
        return IngestFeedResult(
            feed_url=feed_url,
            articles_upserted=len(articles),
            ok=error is None,
            error=error,
        )
