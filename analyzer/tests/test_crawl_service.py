"""Tests CrawlService (orchestration crawl + hooks)."""
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.crawl_service import CrawlService


@pytest.mark.asyncio
async def test_crawl_service_run_maps_result():
    raw = {
        "status": "completed",
        "rss_feeds": [
            {
                "url": "https://example.com/rss",
                "title": "RSS",
                "type": "application/rss+xml",
                "source_page": "https://example.com/",
            }
        ],
        "total_pages_analyzed": 3,
        "site_meta": {"title": "Example"},
    }

    with patch(
        "services.crawl_service._HookedAnalyzer.analyze_site_concurrent",
        new_callable=AsyncMock,
        return_value=raw,
    ):
        pages = []
        feeds = []

        async def on_page(url, title, page_feeds):
            pages.append((url, title, page_feeds))

        async def on_feed(feed):
            feeds.append(feed)

        svc = CrawlService(on_page=on_page, on_feed=on_feed)
        result = await svc.run("https://example.com", max_pages=5, depth=2)

    assert result.status == "completed"
    assert result.total_pages_analyzed == 3
    assert len(result.rss_feeds) == 1
    assert result.rss_feeds[0].url == "https://example.com/rss"
    assert result.site_meta["title"] == "Example"


@pytest.mark.asyncio
async def test_crawl_service_propagates_error_status():
    raw = {
        "status": "error",
        "rss_feeds": [],
        "total_pages_analyzed": 0,
        "error": "timeout",
    }

    with patch(
        "services.crawl_service._HookedAnalyzer.analyze_site_concurrent",
        new_callable=AsyncMock,
        return_value=raw,
    ):
        result = await CrawlService().run("https://example.com")

    assert result.status == "error"
    assert result.error == "timeout"
