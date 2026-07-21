"""Integration Postgres : schema normalise (migrations 006-007)."""
from __future__ import annotations

import pytest

from db_backend import create_pool, is_sqlite_url
from migrate import run_migrations
from repositories.normalized_sync import sync_article_entities, sync_article_media

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_postgres_migration_007_tables(database_url):
    run_migrations(database_url, reset=True)
    pool = await create_pool(database_url)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name IN (
                'article_media', 'article_entities', 'persons', 'article_faces'
              )
            ORDER BY table_name
            """
        )
        names = {r["table_name"] for r in rows}
    await pool.close()
    assert names == {
        "article_faces",
        "article_entities",
        "article_media",
        "persons",
    }


@pytest.mark.asyncio
async def test_postgres_entity_media_id_and_person_link(database_url):
    run_migrations(database_url, reset=True)
    pool = await create_pool(database_url)
    is_sqlite = is_sqlite_url(database_url)

    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO sites (url, status, domain) VALUES ($1, 'ok', 'ex.com')",
            "https://ex.com",
        )
        site = await conn.fetchrow("SELECT id FROM sites LIMIT 1")
        await conn.execute(
            """
            INSERT INTO articles (site_id, feed_url, title, link, enrich_status)
            VALUES ($1, $2, $3, $4, 'ok')
            """,
            int(site["id"]),
            "https://ex.com/feed",
            "Titre",
            "https://ex.com/a1",
        )
        article = await conn.fetchrow("SELECT id FROM articles LIMIT 1")
        article_id = int(article["id"])

        await sync_article_media(
            conn,
            is_sqlite=is_sqlite,
            article_id=article_id,
            media_items=[{"url": "https://ex.com/p.jpg", "alt": "Macron", "source": "rss"}],
            meta={},
            default_type="image",
        )
        media = await conn.fetchrow(
            "SELECT id FROM article_media WHERE article_id = $1 LIMIT 1",
            article_id,
        )
        media_id = int(media["id"])

        await sync_article_entities(
            conn,
            is_sqlite=is_sqlite,
            article_id=article_id,
            entities=[
                {
                    "text": "Emmanuel Macron",
                    "label": "PERSON",
                    "source": "ner_spacy_media",
                    "media_id": media_id,
                }
            ],
        )

        cols = await conn.fetch(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'article_entities'
              AND column_name = 'media_id'
            """
        )
        assert len(cols) == 1

        ent = await conn.fetchrow(
            """
            SELECT person_id, media_id FROM article_entities
            WHERE article_id = $1 AND text = 'Emmanuel Macron'
            """,
            article_id,
        )
        assert ent is not None
        assert ent["media_id"] == media_id
        assert ent["person_id"] is not None

        idx = await conn.fetchrow(
            """
            SELECT 1 FROM pg_indexes
            WHERE tablename = 'persons'
              AND indexname = 'idx_persons_display_name'
            """
        )
        assert idx is not None

    await pool.close()
