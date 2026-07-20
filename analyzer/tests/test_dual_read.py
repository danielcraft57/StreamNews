"""Tests lectures depuis tables normalisees (Phase 3)."""
from __future__ import annotations

import pytest

from database import Database
from db_backend import create_pool
from migrate import run_migrations


@pytest.fixture
def temp_db_url(tmp_path, monkeypatch):
    db_path = tmp_path / "dual_read.db"
    url = f"sqlite:///{db_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    return url


@pytest.mark.asyncio
async def test_get_article_prefers_normalized_tables(temp_db_url):
    run_migrations(temp_db_url, reset=True)
    db = Database()
    db.pool = await create_pool(temp_db_url)

    async with db.pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO sites (url, status, domain, rss_feeds) VALUES ($1, 'ok', 'ex.com', '[]')",
            "https://ex.com",
        )
        site = await conn.fetchrow("SELECT id FROM sites LIMIT 1")

    await db.upsert_article(
        int(site["id"]),
        "https://ex.com/feed.xml",
        "Titre",
        "https://ex.com/a1",
        images=[{"url": "https://ex.com/img.jpg", "source": "rss"}],
        article_meta={"domain": "ex.com", "keywords": ["ia"]},
    )
    await db.update_article_enrichment(
        (await db.get_site_articles(int(site["id"])))[0]["id"],
        content_html="<p>x</p>",
        content_text="x " * 50,
        images=[{"url": "https://ex.com/img.jpg", "source": "og"}],
        article_meta={
            "domain": "ex.com",
            "keywords": ["ia", "tech"],
            "primary_image": "https://ex.com/img.jpg",
            "reading_time_minutes": 2,
        },
        enrich_status="ok",
    )
    articles = await db.get_site_articles(int(site["id"]))
    article_id = articles[0]["id"]

    await db.update_article_analysis(
        article_id,
        analysis={"yake": {"status": "ok", "keywords": ["ia"]}},
        analysis_status="ok",
    )

    # Corrompre le JSON legacy : la lecture doit ignorer et reconstruire
    async with db.pool.acquire() as conn:
        await conn.execute(
            "UPDATE articles SET images = '[]', article_meta = '{}' WHERE id = $1",
            article_id,
        )

    full = await db.get_article(article_id)
    assert full["images"][0]["url"] == "https://ex.com/img.jpg"
    assert full["analysis_status"] == "ok"
    assert full["article_meta"]["domain"] == "ex.com"
    assert "ia" in full["article_meta"]["keywords"]
    assert full["article_meta"]["analysis"]["yake"]["status"] == "ok"

    listed = await db.get_site_articles(int(site["id"]))
    assert listed[0]["images"][0]["url"] == "https://ex.com/img.jpg"
    assert listed[0]["analysis_status"] == "ok"

    site_data = await db.get_site(int(site["id"]))
    assert any("feed.xml" in f["url"] for f in site_data["rss_feeds"])

    await db.close()


@pytest.mark.asyncio
async def test_list_needing_analysis_uses_column(temp_db_url):
    run_migrations(temp_db_url, reset=True)
    db = Database()
    db.pool = await create_pool(temp_db_url)

    async with db.pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO sites (url, status) VALUES ($1, 'ok')",
            "https://z.com",
        )
        site = await conn.fetchrow("SELECT id FROM sites LIMIT 1")
        await conn.execute(
            """
            INSERT INTO articles
                (site_id, feed_url, title, link, dedupe_key, enrich_status, content_text, analysis_status)
            VALUES
                ($1, 'https://z.com/f', 'A', 'https://z.com/a', 'https://z.com/a', 'ok', 'texte', NULL),
                ($1, 'https://z.com/f', 'B', 'https://z.com/b', 'https://z.com/b', 'ok', 'texte', 'ok')
            """,
            site["id"],
        )

    need = await db.list_articles_needing_analysis(int(site["id"]))
    links = {a["link"] for a in need}
    assert "https://z.com/a" in links
    assert "https://z.com/b" not in links

    await db.close()
