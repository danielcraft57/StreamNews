"""Tests NER enrichi + lien PERSON <-> persons / faces."""
from __future__ import annotations

import pytest

from database import Database
from db_backend import create_pool
from migrate import run_migrations
from repositories.normalized_sync import (
    link_persons_from_entities,
    sync_article_entities,
    sync_article_faces,
)
from text_analysis.ner_spacy import normalize_entity_label


@pytest.fixture
def temp_db_url(tmp_path, monkeypatch):
    db_path = tmp_path / "ner007.db"
    url = f"sqlite:///{db_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    return url


def test_normalize_entity_label_fr():
    assert normalize_entity_label("PER") == "PERSON"
    assert normalize_entity_label("person") == "PERSON"
    assert normalize_entity_label("ORG") == "ORG"
    assert normalize_entity_label("loc") == "LOC"


@pytest.mark.asyncio
async def test_migration_007_media_id_on_entities(temp_db_url):
    run_migrations(temp_db_url, reset=True)
    db = Database()
    db.pool = await create_pool(temp_db_url)
    async with db.pool.acquire() as conn:
        cols = await conn.fetch("PRAGMA table_info(article_entities)")
        names = {c["name"] for c in cols}
    assert "media_id" in names
    await db.close()


@pytest.mark.asyncio
async def test_person_link_from_ner_and_face(temp_db_url):
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
        images=[
            {
                "url": "https://ex.com/p.jpg",
                "alt": "Emmanuel Macron a l'Elysee",
                "source": "rss",
            }
        ],
        article_meta={"domain": "ex.com"},
    )

    articles = await db.get_site_articles(int(site["id"]))
    article_id = articles[0]["id"]
    media_id = articles[0]["images"][0]["id"]

    async with db.pool.acquire() as conn:
        await sync_article_entities(
            conn,
            is_sqlite=True,
            article_id=article_id,
            entities=[
                {
                    "text": "Emmanuel Macron",
                    "label": "PER",
                    "start_char": 0,
                    "end_char": 15,
                    "source": "ner_spacy",
                },
                {
                    "text": "Emmanuel Macron",
                    "label": "PERSON",
                    "source": "ner_spacy_media",
                    "media_id": media_id,
                },
                {"text": "Paris", "label": "LOC"},
            ],
        )

        ent = await conn.fetchrow(
            """
            SELECT label, person_id, start_char, end_char
            FROM article_entities
            WHERE article_id = $1 AND text = 'Emmanuel Macron' AND source = 'ner_spacy'
            """,
            article_id,
        )
        assert ent is not None
        assert ent["label"] == "PERSON"
        assert ent["person_id"] is not None
        assert ent["start_char"] == 0
        assert ent["end_char"] == 15

        person = await conn.fetchrow(
            "SELECT id, display_name FROM persons WHERE id = $1",
            ent["person_id"],
        )
        assert person["display_name"] == "Emmanuel Macron"

        await sync_article_faces(
            conn,
            is_sqlite=True,
            article_id=article_id,
            faces=[
                {
                    "media_id": media_id,
                    "bbox": {"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.4},
                    "confidence": 0.9,
                }
            ],
        )
        # Relancer le lien faces apres insert faces
        await link_persons_from_entities(
            conn, is_sqlite=True, article_id=article_id
        )

        face = await conn.fetchrow(
            "SELECT person_id FROM article_faces WHERE article_id = $1",
            article_id,
        )
        assert face["person_id"] == ent["person_id"]

    await db.close()
