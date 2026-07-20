"""Tests migration 002 et backfill normalise."""
from __future__ import annotations

import json

import pytest

from backfill_normalized import backfill_normalized
from database import Database
from db_backend import create_pool
from migrate import run_migrations


@pytest.fixture
def temp_db_url(tmp_path, monkeypatch):
    db_path = tmp_path / "norm_test.db"
    url = f"sqlite:///{db_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    return url


@pytest.mark.asyncio
async def test_migration_002_creates_normalized_tables(temp_db_url):
    run_migrations(temp_db_url, reset=True)

    db = Database()
    db.pool = await create_pool(temp_db_url)
    try:
        async with db.pool.acquire() as conn:
            tables = await conn.fetch(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            names = {r["name"] for r in tables}
        assert "rss_feeds" in names
        assert "article_images" in names
        assert "article_keywords" in names
        assert "article_analyses" in names
        assert "article_meta_norm" in names
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_backfill_from_legacy_json(temp_db_url):
    run_migrations(temp_db_url, reset=True)

    db = Database()
    db.pool = await create_pool(temp_db_url)

    async with db.pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO sites (url, status, rss_feeds, domain)
            VALUES ($1, 'ok', $2, 'example.com')
            """,
            "https://example.com",
            json.dumps([{"url": "https://example.com/feed.xml", "title": "Main", "type": "rss"}]),
        )
        site = await conn.fetchrow("SELECT id FROM sites LIMIT 1")
        await conn.execute(
            """
            INSERT INTO articles
                (site_id, feed_url, title, link, images, article_meta)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            site["id"],
            "https://example.com/feed.xml",
            "Test",
            "https://example.com/a1",
            json.dumps([{"url": "https://example.com/img.jpg", "source": "rss"}]),
            json.dumps(
                {
                    "keywords": ["python", "news"],
                    "domain": "example.com",
                    "analysis_status": "ok",
                    "analysis": {
                        "langdetect": {"status": "ok", "language": "fr"},
                    },
                }
            ),
        )

    stats = await backfill_normalized(db)
    assert stats["rss_feeds"] >= 1
    assert stats["article_images"] >= 1
    assert stats["article_keywords"] >= 2
    assert stats["article_analyses"] >= 1
    assert stats["article_meta_norm"] >= 1

    async with db.pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT feed_id, analysis_status FROM articles WHERE link = $1",
            "https://example.com/a1",
        )
        assert row["feed_id"] is not None
        assert row["analysis_status"] == "ok"

        kw_count = await conn.fetchrow(
            "SELECT COUNT(*) AS c FROM article_keywords WHERE article_id = "
            "(SELECT id FROM articles WHERE link = $1)",
            "https://example.com/a1",
        )
        assert kw_count["c"] >= 2

    await db.close()
