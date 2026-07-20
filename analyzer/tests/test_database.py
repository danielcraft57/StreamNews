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


@pytest.mark.asyncio
async def test_create_site_analysis():
    db = Database()
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(
        side_effect=[
            None,  # pas de site existant
            {"id": 42},
        ]
    )
    mock_conn.execute = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    db.pool = mock_pool

    site_id = await db.create_site_analysis("https://example.com", "pending")
    assert site_id == 42
    assert mock_conn.fetchrow.await_count == 2


def test_merge_rss_feeds_dedupes_urls(monkeypatch):
    import utils.feeds as feeds_mod

    monkeypatch.setattr(
        feeds_mod,
        "collapse_equivalent_feeds",
        lambda feeds, **kwargs: list(feeds),
    )
    # re-import path used inside merge
    monkeypatch.setattr(
        "utils.collapse_equivalent_feeds",
        lambda feeds, **kwargs: list(feeds),
    )

    existing = [{"url": "https://example.com/rss", "title": "A"}]
    new = [
        {"url": "http://example.com/rss/", "title": "B"},
        {"url": "https://example.com/atom", "title": "C"},
    ]
    merged = Database.merge_rss_feeds(existing, new)
    urls = {f["url"] for f in merged}
    assert "https://example.com/rss" in urls
    assert "https://example.com/atom" in urls
    assert len(merged) == 2


@pytest.mark.asyncio
async def test_add_page_analysis_serializes_feeds():
    db = Database()
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=None)
    mock_conn.execute = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    db.pool = mock_pool

    feeds = [{"url": "https://example.com/rss", "title": "Feed"}]
    await db.add_page_analysis(1, "https://example.com/page", "Title", feeds)

    args = mock_conn.execute.await_args.args
    assert args[1] == 1
    assert args[2] == "https://example.com/page"
    assert args[3] == "Title"
    assert json.loads(args[4]) == feeds


@pytest.mark.asyncio
async def test_cleanup_old_analyses_returns_count():
    db = Database()
    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock(side_effect=["DELETE 3", "DELETE 2", "DELETE 2"])

    mock_tx = MagicMock()
    mock_tx.__aenter__ = AsyncMock(return_value=None)
    mock_tx.__aexit__ = AsyncMock(return_value=None)
    mock_conn.transaction = MagicMock(return_value=mock_tx)

    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    db.pool = mock_pool

    deleted = await db.cleanup_old_analyses(30)
    assert deleted == 2
    assert mock_conn.execute.await_count == 3
