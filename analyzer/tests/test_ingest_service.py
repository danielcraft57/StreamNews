"""Tests service d'ingestion RSS (parse feed -> articles)."""
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.ingest_service import IngestService


def _entry(**kwargs):
    e = MagicMock()
    for k, v in kwargs.items():
        setattr(e, k, v)
    e.get = lambda key, default=None: kwargs.get(key, default)
    return e


def _mock_http_and_parse(monkeypatch, parsed):
    """IngestService telecharge via requests puis parse le body."""
    resp = MagicMock()
    resp.content = b"<rss/>"
    resp.raise_for_status = MagicMock()
    monkeypatch.setattr(
        "services.ingest_service.requests.get",
        lambda *a, **k: resp,
    )
    monkeypatch.setattr(
        "services.ingest_service.feedparser.parse",
        lambda raw: parsed,
    )


def test_parse_feed_extracts_articles(monkeypatch):
    parsed = MagicMock()
    parsed.entries = [
        _entry(
            title="Article 1",
            link="https://example.com/post-1",
            summary="Resume court",
            author="Alice",
            id="guid-1",
        ),
        _entry(
            title="Article 2",
            link="http://www.example.com/post-2/",
            description="Desc",
        ),
        _entry(title="Sans lien", link=""),
    ]
    _mock_http_and_parse(monkeypatch, parsed)

    svc = IngestService(max_entries=10)
    articles = svc.parse_feed("https://example.com/rss")

    assert len(articles) == 2
    assert articles[0].title == "Article 1"
    assert articles[0].link == "https://example.com/post-1"
    assert articles[0].guid == "guid-1"
    assert articles[1].link == "https://example.com/post-2"


def test_parse_feed_truncates_long_summary(monkeypatch):
    parsed = MagicMock()
    parsed.entries = [
        _entry(
            title="Long",
            link="https://example.com/x",
            summary="x" * 5000,
        ),
    ]
    _mock_http_and_parse(monkeypatch, parsed)

    svc = IngestService(summary_max_len=100)
    articles = svc.parse_feed("https://example.com/rss")

    assert len(articles[0].summary) == 101  # 100 + ellipsis char
    assert articles[0].summary.endswith("…")


def test_parse_feed_handles_parse_error(monkeypatch):
    def _boom(*_a, **_k):
        raise RuntimeError("network down")

    monkeypatch.setattr("services.ingest_service.requests.get", _boom)
    articles = IngestService().parse_feed("https://example.com/rss")
    assert articles == []


def test_parse_feed_published_date(monkeypatch):
    parsed = MagicMock()
    parsed.entries = [
        _entry(
            title="Dated",
            link="https://example.com/d",
            published_parsed=(2026, 7, 19, 10, 0, 0, 0, 0, 0),
        ),
    ]
    _mock_http_and_parse(monkeypatch, parsed)

    articles = IngestService().parse_feed("https://example.com/rss")
    assert isinstance(articles[0].published_at, datetime)


def test_result_model():
    from models import ArticleCandidate

    svc = IngestService()
    arts = [
        ArticleCandidate(feed_url="https://x/rss", title="T", link="https://x/a"),
    ]
    r = svc.result("https://x/rss", arts)
    assert r.ok is True
    assert r.articles_upserted == 1
