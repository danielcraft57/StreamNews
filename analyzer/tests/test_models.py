"""Smoke tests architecture pipeline (imports + models)."""
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.modules.setdefault("aiohttp", MagicMock())
sys.modules.setdefault("feedparser", MagicMock())
sys.modules.setdefault("bs4", MagicMock())
try:
    import asyncpg  # noqa: F401
except ImportError:
    sys.modules["asyncpg"] = MagicMock()
sys.modules.setdefault("celery", MagicMock())
sys.modules.setdefault("requests", MagicMock())

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models import ArticleCandidate, CrawlResult, FeedRef


def test_feed_ref_model():
    f = FeedRef(url="https://example.com/rss", title="News")
    assert f.url.endswith("/rss")
    assert f.model_dump()["title"] == "News"


def test_crawl_result_defaults():
    r = CrawlResult()
    assert r.status == "completed"
    assert r.rss_feeds == []


def test_article_candidate():
    a = ArticleCandidate(feed_url="https://x/rss", title="Hi", link="https://x/1")
    assert a.link.endswith("/1")
