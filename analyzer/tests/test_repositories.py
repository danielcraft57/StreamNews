"""Tests repositories entites (architecture lecture)."""
from __future__ import annotations

import pytest

from database import Database
from db_backend import create_pool
from migrate import run_migrations
from models.entities import ArticleRecord, SiteRecord
from repositories.articles_repo import ArticlesRepository
from repositories.sites_repo import SitesRepository


@pytest.fixture
def temp_db_url(tmp_path, monkeypatch):
    db_path = tmp_path / "repo_entities.db"
    url = f"sqlite:///{db_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    return url


@pytest.mark.asyncio
async def test_articles_repo_returns_entity(temp_db_url):
    run_migrations(temp_db_url, reset=True)
    db = Database()
    db.pool = await create_pool(temp_db_url)

    async with db.pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO sites (url, status, domain) VALUES ($1, 'ok', 'ex.com')",
            "https://ex.com",
        )
        site = await conn.fetchrow("SELECT id FROM sites LIMIT 1")

    await db.upsert_article(
        int(site["id"]),
        "https://ex.com/feed.xml",
        "Hello",
        "https://ex.com/p1",
        images=[{"url": "https://ex.com/i.jpg", "source": "rss"}],
        article_meta={"domain": "ex.com", "keywords": ["news"]},
    )
    await db.update_article_analysis(
        (await db.get_site_articles(int(site["id"])))[0]["id"],
        analysis={"langdetect": {"status": "ok", "language": "fr"}},
        analysis_status="ok",
    )

    repo = ArticlesRepository(db.pool, is_sqlite=True)
    listed = await repo.list_by_site(int(site["id"]))
    assert len(listed) == 1
    assert isinstance(listed[0], ArticleRecord)
    assert listed[0].images[0].url.endswith("i.jpg")
    assert listed[0].keywords[0].keyword == "news"

    detail = await repo.get_by_id(listed[0].id)
    assert detail is not None
    assert detail.analysis_status == "ok"
    assert detail.analyses[0].tool_name == "langdetect"

    api = detail.to_api_dict()
    assert api["article_meta"]["analysis"]["langdetect"]["language"] == "fr"
    assert api["images"][0]["url"].endswith("i.jpg")

    await db.close()


@pytest.mark.asyncio
async def test_sites_repo_returns_entity_with_feeds(temp_db_url):
    run_migrations(temp_db_url, reset=True)
    db = Database()
    db.pool = await create_pool(temp_db_url)

    async with db.pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO sites (url, status, domain) VALUES ($1, 'ok', 'news.test')",
            "https://news.test",
        )
        site = await conn.fetchrow("SELECT id FROM sites LIMIT 1")

    await db.update_site_status(
        int(site["id"]),
        "ok",
        rss_feeds=[{"url": "https://news.test/rss", "title": "Main", "type": "rss"}],
        merge_feeds=False,
    )

    repo = SitesRepository(db.pool, is_sqlite=True)
    record = await repo.get_by_id(int(site["id"]))
    assert isinstance(record, SiteRecord)
    assert len(record.rss_feeds) == 1
    assert record.rss_feeds[0].url.endswith("/rss")
    assert record.to_api_dict()["rss_feeds"][0]["type"] == "rss"

    await db.close()
