"""Tests face_detect optionnel (sans deps lourdes)."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from database import Database
from db_backend import create_pool
from migrate import run_migrations
from repositories.normalized_sync import match_faces_by_embedding, sync_article_faces
from text_analysis.face_backends import (
    embeddings_match,
    pack_embedding,
    unpack_embedding,
)
from text_analysis.face_detect import FaceDetectAnalyzer, face_detect_enabled
from text_analysis.runner import list_analyzers, run_analyzers


@pytest.fixture
def temp_db_url(tmp_path, monkeypatch):
    db_path = tmp_path / "faces_opt.db"
    url = f"sqlite:///{db_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    return url


def test_face_detect_disabled_by_default(monkeypatch):
    monkeypatch.delenv("FACE_DETECT_ENABLED", raising=False)
    assert face_detect_enabled() is False
    info = next(a for a in list_analyzers() if a["name"] == "face_detect")
    assert info["optional"] is True
    assert info["enabled"] is False


def test_face_detect_excluded_from_default_run(monkeypatch):
    monkeypatch.delenv("FACE_DETECT_ENABLED", raising=False)
    results = run_analyzers("Ceci est un texte assez long pour les analyseurs de base.")
    assert "face_detect" not in results


def test_face_detect_skip_when_disabled(monkeypatch):
    monkeypatch.setenv("FACE_DETECT_ENABLED", "0")
    block = FaceDetectAnalyzer().analyze(
        "",
        media_items=[{"url": "https://ex.com/a.jpg", "media_id": 1}],
    )
    assert block["status"] == "skipped"
    assert "desactive" in block.get("reason", "")


def test_face_detect_runs_when_enabled_with_mock(monkeypatch):
    monkeypatch.setenv("FACE_DETECT_ENABLED", "1")
    monkeypatch.setenv("FACE_DETECT_BACKEND", "face_recognition")

    fake_faces = [
        {
            "media_id": 7,
            "bbox": {"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.4, "unit": "ratio"},
            "confidence": 0.95,
            "embedding": pack_embedding([0.1] * 128),
            "embedding_dim": 128,
            "match_metric": "euclidean",
            "backend": "face_recognition",
        }
    ]

    import sys
    import types

    monkeypatch.setitem(sys.modules, "face_recognition", types.ModuleType("face_recognition"))

    with patch(
        "text_analysis.face_backends.run_backend_on_media",
        return_value=(fake_faces, []),
    ):
        block = FaceDetectAnalyzer().analyze(
            "",
            media_items=[{"url": "https://ex.com/a.jpg", "media_id": 7}],
        )

    assert block["status"] == "ok"
    assert block["face_count"] == 1
    assert block["faces"][0]["media_id"] == 7


def test_pack_unpack_embedding_roundtrip():
    vals = [0.1, -0.2, 0.5, 1.0]
    blob = pack_embedding(vals)
    assert isinstance(blob, bytes)
    back = unpack_embedding(blob)
    assert len(back) == 4
    assert abs(back[0] - 0.1) < 1e-6


def test_embeddings_match_euclidean():
    a = [0.0] * 128
    b = [0.01] * 128
    assert embeddings_match(a, b, metric="euclidean") is True
    c = [1.0] * 128
    assert embeddings_match(a, c, metric="euclidean") is False


@pytest.mark.asyncio
async def test_match_faces_by_embedding_links_person(temp_db_url):
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
    )
    articles = await db.get_site_articles(int(site["id"]))
    article_id = articles[0]["id"]
    media_id = articles[0]["images"][0]["id"]

    emb_a = pack_embedding([0.05] * 128)
    emb_b = pack_embedding([0.06] * 128)  # proche -> match

    async with db.pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO persons (display_name, meta) VALUES ($1, '{}')",
            "Alice Test",
        )
        person = await conn.fetchrow("SELECT id FROM persons LIMIT 1")
        pid = int(person["id"])

        await sync_article_faces(
            conn,
            is_sqlite=True,
            article_id=article_id,
            faces=[
                {
                    "media_id": media_id,
                    "person_id": pid,
                    "bbox": {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2},
                    "embedding": emb_a,
                    "embedding_dim": 128,
                }
            ],
            link_persons=False,
        )
        await sync_article_faces(
            conn,
            is_sqlite=True,
            article_id=article_id,
            faces=[
                {
                    "media_id": media_id,
                    "bbox": {"x": 0.5, "y": 0.5, "w": 0.2, "h": 0.2},
                    "embedding": emb_b,
                    "embedding_dim": 128,
                }
            ],
            link_persons=False,
        )
        n = await match_faces_by_embedding(conn, article_id=article_id)
        assert n >= 1
        row = await conn.fetchrow(
            """
            SELECT person_id FROM article_faces
            WHERE article_id = $1 AND person_id IS NOT NULL
            ORDER BY id DESC LIMIT 1
            """,
            article_id,
        )
        assert int(row["person_id"]) == pid

    await db.close()
