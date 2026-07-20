"""Tests migration 006 medias / entities / faces."""
from __future__ import annotations

import pytest

from database import Database
from db_backend import create_pool
from migrate import run_migrations
from repositories.normalized_sync import sync_article_entities, sync_article_media


@pytest.fixture
def temp_db_url(tmp_path, monkeypatch):
    db_path = tmp_path / "media006.db"
    url = f"sqlite:///{db_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    return url


@pytest.mark.asyncio
async def test_migration_006_media_entities_faces(temp_db_url):
    run_migrations(temp_db_url, reset=True)
    db = Database()
    db.pool = await create_pool(temp_db_url)
    async with db.pool.acquire() as conn:
        tables = await conn.fetch(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        names = {r["name"] for r in tables}
    assert "article_media" in names
    assert "article_entities" in names
    assert "persons" in names
    assert "article_faces" in names
    assert "article_images" not in names
    await db.close()


@pytest.mark.asyncio
async def test_sync_media_multi_types_and_entities(temp_db_url):
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
        "https://ex.com/feed",
        "Titre",
        "https://ex.com/a1",
        images=[{"url": "https://ex.com/p.jpg", "source": "rss"}],
        videos=[{"url": "https://ex.com/v.mp4", "mime_type": "video/mp4"}],
        audios=[{"url": "https://ex.com/a.mp3", "mime_type": "audio/mpeg"}],
        article_meta={"domain": "ex.com"},
    )

    articles = await db.get_site_articles(int(site["id"]))
    article_id = articles[0]["id"]
    assert articles[0]["images"]
    assert articles[0]["videos"]
    assert articles[0]["audios"]

    await db.update_article_analysis(
        article_id,
        analysis={
            "ner_spacy": {
                "status": "ok",
                "entities": [
                    {"text": "Macron", "label": "PER"},
                    {"text": "Paris", "label": "LOC"},
                ],
            }
        },
        analysis_status="ok",
    )

    full = await db.get_article(article_id)
    macron = next(e for e in (full.get("entities") or []) if e["text"] == "Macron")
    assert macron["label"] == "PERSON"
    assert macron.get("person_id") is not None
    assert any(e["text"] == "Paris" for e in full.get("entities") or [])

    async with db.pool.acquire() as conn:
        await sync_article_media(
            conn,
            is_sqlite=True,
            article_id=article_id,
            media_items=[{"url": "https://ex.com/extra.jpg"}],
            meta={},
            default_type="image",
        )
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM article_media WHERE article_id = $1",
            article_id,
        )
        assert count >= 3

        await sync_article_entities(
            conn,
            is_sqlite=True,
            article_id=article_id,
            entities=[{"text": "France", "label": "LOC"}],
        )

    await db.close()


@pytest.mark.asyncio
async def test_face_detect_listed(temp_db_url):
    from text_analysis.runner import list_analyzers

    names = {a["name"] for a in list_analyzers()}
    assert "face_detect" in names
    assert "ner_spacy" in names
