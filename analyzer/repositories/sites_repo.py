"""Repository sites : lectures normalisees -> entites Pydantic."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from models.entities import RssFeedRecord, SiteRecord
from repositories.normalized_sync import has_normalized_tables


def _parse_json(value: Any, default: Any):
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, (bytes, bytearray)):
        value = value.decode()
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return default
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return default


def _as_dt(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


class SitesRepository:
    def __init__(self, pool, *, is_sqlite: bool):
        self.pool = pool
        self.is_sqlite = is_sqlite

    async def _feeds_for_site(self, conn, site_id: int) -> List[RssFeedRecord]:
        rows = await conn.fetch(
            """
            SELECT id, site_id, url, title, feed_type, source_page_id, created_at
            FROM rss_feeds
            WHERE site_id = $1
            ORDER BY id ASC
            """,
            site_id,
        )
        return [
            RssFeedRecord(
                id=int(r["id"]),
                site_id=int(r["site_id"]),
                url=r["url"],
                title=r["title"] or "Flux RSS",
                feed_type=r["feed_type"] or "detected",
                source_page_id=r["source_page_id"],
                created_at=_as_dt(r.get("created_at")),
            )
            for r in rows
        ]

    def _from_row(self, row: Dict[str, Any], feeds: List[RssFeedRecord]) -> SiteRecord:
        extra = _parse_json(row.get("meta_extra"), {})
        if not isinstance(extra, dict):
            extra = {}
        return SiteRecord(
            id=int(row["id"]),
            url=row["url"],
            status=row.get("status") or "pending",
            domain=row.get("domain"),
            site_title=row.get("site_title"),
            favicon_url=row.get("favicon_url"),
            meta_description=row.get("meta_description"),
            meta_extra=extra,
            total_pages_analyzed=int(row.get("total_pages_analyzed") or 0),
            celery_task_id=row.get("celery_task_id"),
            created_at=_as_dt(row.get("created_at")),
            updated_at=_as_dt(row.get("updated_at")),
            rss_feeds=feeds,
        )

    async def get_by_id(self, site_id: int) -> Optional[SiteRecord]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM sites WHERE id = $1", site_id)
            if not row:
                return None
            feeds: List[RssFeedRecord] = []
            if await has_normalized_tables(conn, is_sqlite=self.is_sqlite):
                feeds = await self._feeds_for_site(conn, site_id)
            return self._from_row(dict(row), feeds)

    async def list_all(self) -> List[SiteRecord]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM sites ORDER BY created_at DESC")
            if not rows:
                return []
            has_norm = await has_normalized_tables(conn, is_sqlite=self.is_sqlite)
            out: List[SiteRecord] = []
            for row in rows:
                feeds = (
                    await self._feeds_for_site(conn, int(row["id"])) if has_norm else []
                )
                out.append(self._from_row(dict(row), feeds))
            return out
