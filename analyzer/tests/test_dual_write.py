"""Tests dual-write JSON legacy + tables normalisees (Phase 2)."""
from __future__ import annotations

import json

import pytest

from database import Database
from db_backend import create_pool
from migrate import run_migrations


@pytest.fixture
def temp_db_url(tmp_path, monkeypatch):
    db_path = tmp_path / "dual_write.db"
    url = f"sqlite:///{db_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    return url


@pytest.mark.asyncio
async def test_upsert_article_dual_writes_feed_and_images(temp_db_url):
    run_migrations(temp_db_url, reset=True)
    db = Database()
    db.pool = await create_pool(temp_db_url)

    async with db.pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO sites (url, status, rss_feeds, domain)
            VALUES ($1, 'ok', '[]', 'example.com')
            """,
            "https://example.com",
        )
        site = await conn.fetchrow("SELECT id FROM sites LIMIT 1")

    ok = await db.upsert_article(
        int(site["id"]),
        "https://example.com/feed.xml",
        "Hello",
        "https://example.com/post-1",
        images=[{"url": "https://example.com/hero.jpg", "source": "rss"}],
        article_meta={"keywords": ["tech"], "domain": "example.com"},
    )
    assert ok is True

    async with db.pool.acquire() as conn:
        art = await conn.fetchrow(
            "SELECT id, feed_id FROM articles WHERE link LIKE '%post-1%'"
        )
        assert art["feed_id"] is not None

        feed = await conn.fetchrow("SELECT url FROM rss_feeds WHERE id = $1", art["feed_id"])
        assert "feed.xml" in feed["url"]

        img_count = await conn.fetchval(
            "SELECT COUNT(*) FROM article_images WHERE article_id = $1",
            art["id"],
        )
        assert img_count >= 1

        kw_count = await conn.fetchval(
            "SELECT COUNT(*) FROM article_keywords WHERE article_id = $1",
            art["id"],
        )
        assert kw_count >= 1

    await db.close()


@pytest.mark.asyncio
async def test_update_article_analysis_dual_writes(temp_db_url):
    run_migrations(temp_db_url, reset=True)
    db = Database()
    db.pool = await create_pool(temp_db_url)

    async with db.pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO sites (url, status, domain) VALUES ($1, 'ok', 'ex.com')",
            "https://ex.com",
        )
        site = await conn.fetchrow("SELECT id FROM sites LIMIT 1")
        await conn.execute(
            """
            INSERT INTO articles (site_id, feed_url, title, link, dedupe_key, article_meta)
            VALUES ($1, $2, $3, $4, $5, '{}')
            """,
            site["id"],
            "https://ex.com/feed",
            "T",
            "https://ex.com/a",
            "https://ex.com/a",
        )
        art = await conn.fetchrow("SELECT id FROM articles LIMIT 1")

    await db.update_article_analysis(
        int(art["id"]),
        analysis={"langdetect": {"status": "ok", "language": "fr"}},
        analysis_status="ok",
    )

    async with db.pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT analysis_status, article_meta FROM articles WHERE id = $1",
            art["id"],
        )
        assert row["analysis_status"] == "ok"
        meta = json.loads(row["article_meta"]) if isinstance(row["article_meta"], str) else row["article_meta"]
        assert meta.get("analysis_status") == "ok"

        tool = await conn.fetchrow(
            "SELECT tool_name, status FROM article_analyses WHERE article_id = $1",
            art["id"],
        )
        assert tool["tool_name"] == "langdetect"
        assert tool["status"] == "ok"

    await db.close()


@pytest.mark.asyncio
async def test_update_site_status_syncs_rss_feeds(temp_db_url):
    run_migrations(temp_db_url, reset=True)
    db = Database()
    db.pool = await create_pool(temp_db_url)

    async with db.pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO sites (url, status, rss_feeds) VALUES ($1, 'pending', '[]')",
            "https://news.test",
        )
        site = await conn.fetchrow("SELECT id FROM sites LIMIT 1")

    await db.update_site_status(
        int(site["id"]),
        "ok",
        rss_feeds=[{"url": "https://news.test/rss.xml", "title": "Main", "type": "rss"}],
        merge_feeds=False,
    )

    async with db.pool.acquire() as conn:
        count = await conn.fetchval("SELECT COUNT(*) FROM rss_feeds WHERE site_id = $1", site["id"])
        assert count == 1

    await db.close()
