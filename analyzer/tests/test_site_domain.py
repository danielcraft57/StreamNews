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
async def test_update_site_status_merges_feeds():
    db = Database()
    mock_conn = AsyncMock()
    existing = [{"url": "https://bfmtv.com/rss", "title": "RSS"}]
    mock_conn.fetchrow = AsyncMock(
        side_effect=[{"rss_feeds": json.dumps(existing)}, None]
    )
    mock_conn.execute = AsyncMock()
    db.pool = _mock_pool(mock_conn)

    new_feeds = [{"url": "https://bfmtv.com/atom.xml", "title": "Atom"}]
    await db.update_site_status(1, "completed", new_feeds, 10, merge_feeds=True)

    args = mock_conn.execute.await_args.args
    stored = json.loads(args[2])
    urls = {f["url"] for f in stored}
    assert "https://bfmtv.com/rss" in urls
    assert "https://bfmtv.com/atom.xml" in urls


@pytest.mark.asyncio
async def test_update_site_status_can_replace_feeds():
    db = Database()
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=None)
    mock_conn.execute = AsyncMock()
    db.pool = _mock_pool(mock_conn)

    feeds = [{"url": "https://example.com/only", "title": "Only"}]
    await db.update_site_status(1, "completed", feeds, 5, merge_feeds=False)

    mock_conn.fetchrow.assert_awaited_once()
    stored = json.loads(mock_conn.execute.await_args.args[2])
    assert len(stored) == 1


@pytest.mark.asyncio
async def test_ensure_site_domain_unique_merges_duplicates():
    db = Database()
    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(
        return_value=[
            {
                "id": 1,
                "url": "https://www.bfmtv.com/",
                "domain": None,
                "rss_feeds": json.dumps(
                    [{"url": "https://bfmtv.com/rss-a", "title": "A"}]
                ),
            },
            {
                "id": 2,
                "url": "https://bfmtv.com/actu",
                "domain": None,
                "rss_feeds": json.dumps(
                    [{"url": "https://bfmtv.com/rss-b", "title": "B"}]
                ),
            },
        ]
    )
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
