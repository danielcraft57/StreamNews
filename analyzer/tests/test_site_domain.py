"""Tests unicite domaine + fusion feeds (unit, sans Postgres)."""
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

try:
    import asyncpg  # noqa: F401
except ImportError:
    sys.modules["asyncpg"] = MagicMock()
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import Database


def _mock_pool(mock_conn):
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    return mock_pool


@pytest.mark.asyncio
async def test_upsert_site_creates_new():
    db = Database()
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(
        side_effect=[None, {"id": 7}]
    )
    mock_conn.execute = AsyncMock()
    db.pool = _mock_pool(mock_conn)

    result = await db.upsert_site_for_analysis("https://www.bfmtv.com/", "pending")

    assert result["site_id"] == 7
    assert result["reused"] is False
    assert result["domain"] == "bfmtv.com"
    insert_call = mock_conn.fetchrow.await_args_list[-1]
    assert "INSERT INTO sites" in insert_call.args[0]


@pytest.mark.asyncio
async def test_upsert_site_reuses_same_domain():
    db = Database()
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(
        return_value={
            "id": 3,
            "celery_task_id": "old-task-abc",
            "status": "completed",
        }
    )
    mock_conn.execute = AsyncMock()
    db.pool = _mock_pool(mock_conn)

    result = await db.upsert_site_for_analysis(
        "https://bfmtv.com/rss-section", "pending"
    )

    assert result["site_id"] == 3
    assert result["reused"] is True
    assert result["domain"] == "bfmtv.com"
    assert result["old_task_id"] == "old-task-abc"
    mock_conn.execute.assert_awaited_once()
    assert "UPDATE sites SET" in mock_conn.execute.await_args.args[0]


@pytest.mark.asyncio
async def test_upsert_site_rejects_invalid_url():
    db = Database()
    db.pool = _mock_pool(AsyncMock())

    with pytest.raises(ValueError, match="domaine"):
        await db.upsert_site_for_analysis("", "pending")


@pytest.mark.asyncio
async def test_update_site_status_merges_feeds(monkeypatch):
    # Unit isole : SQLite + pas de fetch reseau (collapse_equivalent_feeds).
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./data/streamnews.db")
    monkeypatch.setattr(
        "utils.feeds.collapse_equivalent_feeds",
        lambda feeds, **kwargs: list(feeds or []),
    )
    db = Database()
    assert db.is_sqlite is True
    mock_conn = AsyncMock()
    existing_rows = [
        {
            "url": "https://bfmtv.com/rss",
            "title": "RSS",
            "feed_type": "detected",
            "source_page_id": None,
        }
    ]
    mock_conn.fetch = AsyncMock(return_value=existing_rows)
    mock_conn.fetchrow = AsyncMock(return_value={"id": 1})
    mock_conn.execute = AsyncMock()
    db.pool = _mock_pool(mock_conn)

    new_feeds = [{"url": "https://bfmtv.com/atom.xml", "title": "Atom"}]
    await db.update_site_status(1, "completed", new_feeds, 10, merge_feeds=True)

    update_sql = mock_conn.execute.await_args_list[0].args[0]
    assert "UPDATE sites SET status" in update_sql
    assert "rss_feeds" not in update_sql
    # UPDATE sites + INSERT OR IGNORE par feed synchronise
    assert mock_conn.execute.await_count >= 2
    assert any("INSERT" in c.args[0] and "rss_feeds" in c.args[0] for c in mock_conn.execute.await_args_list)


@pytest.mark.asyncio
async def test_update_site_status_can_replace_feeds(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./data/streamnews.db")
    monkeypatch.setattr(
        "utils.feeds.collapse_equivalent_feeds",
        lambda feeds, **kwargs: list(feeds or []),
    )
    db = Database()
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value={"id": 9})
    mock_conn.execute = AsyncMock()
    db.pool = _mock_pool(mock_conn)

    feeds = [{"url": "https://example.com/only", "title": "Only"}]
    await db.update_site_status(1, "completed", feeds, 5, merge_feeds=False)

    update_sql = mock_conn.execute.await_args_list[0].args[0]
    assert "UPDATE sites SET status" in update_sql
    assert mock_conn.execute.await_args_list[0].args[1:] == ("completed", 5, 1)


@pytest.mark.asyncio
async def test_ensure_site_domain_unique_merges_duplicates(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost/db")
    db = Database()
    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(
        side_effect=[
            [
                {
                    "id": 1,
                    "url": "https://www.bfmtv.com/",
                    "domain": None,
                },
                {
                    "id": 2,
                    "url": "https://bfmtv.com/actu",
                    "domain": None,
                },
            ],
            # load_site_rss_feeds for site 1 then site 2
            [{"url": "https://bfmtv.com/rss-a", "title": "A", "feed_type": "rss", "source_page_id": None}],
            [{"url": "https://bfmtv.com/rss-b", "title": "B", "feed_type": "rss", "source_page_id": None}],
        ]
    )
    mock_conn.fetchrow = AsyncMock(return_value={"id": 1})
    mock_conn.execute = AsyncMock()
    db.pool = _mock_pool(mock_conn)

    deleted = await db.ensure_site_domain_unique()

    assert deleted == 1
    sql_calls = [c.args[0] for c in mock_conn.execute.await_args_list]
    assert any("DELETE FROM sites" in s for s in sql_calls)
    assert any("UPDATE articles" in s for s in sql_calls)


def test_merge_rss_feeds_keeps_existing_title(monkeypatch):
    import utils.feeds as feeds_mod

    monkeypatch.setattr(
        feeds_mod,
        "collapse_equivalent_feeds",
        lambda feeds, **kwargs: list(feeds),
    )

    existing = [{"url": "https://bfmtv.com/rss", "title": "Titre RSS"}]
    new = [{"url": "http://www.bfmtv.com/rss/", "title": ""}]
    merged = Database.merge_rss_feeds(existing, new)

    assert len(merged) == 1
    assert merged[0]["title"] == "Titre RSS"
    assert merged[0]["url"] == "https://bfmtv.com/rss"
