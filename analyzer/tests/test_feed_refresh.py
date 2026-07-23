"""Helpers refresh feeds (cron)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tasks import _feed_urls_from_site


def test_feed_urls_from_site_dedupes():
    site = {
        "rss_feeds": [
            {"url": "https://example.com/feed.xml"},
            {"url": "https://example.com/feed.xml"},
            {"url": " https://example.com/atom.xml "},
            {"title": "no url"},
            "https://plain.example/rss",
        ]
    }
    urls = _feed_urls_from_site(site)
    assert urls == [
        "https://example.com/feed.xml",
        "https://example.com/atom.xml",
        "https://plain.example/rss",
    ]


def test_beat_includes_feed_refresh():
    from celery_app import celery_app, FEED_REFRESH_MINUTES

    assert "refresh-all-feeds" in celery_app.conf.beat_schedule
    assert FEED_REFRESH_MINUTES >= 5
