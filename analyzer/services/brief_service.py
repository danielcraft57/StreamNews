"""Brief hebdo + quotidien : top tendances + radar."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional


def week_start_iso(dt: Optional[datetime] = None) -> str:
    now = dt or datetime.now(timezone.utc).replace(tzinfo=None)
    monday = now - timedelta(days=now.weekday())
    return monday.date().isoformat()


def day_iso(dt: Optional[datetime] = None) -> str:
    now = dt or datetime.now(timezone.utc).replace(tzinfo=None)
    return now.date().isoformat()


class BriefService:
    def __init__(self, db):
        self.db = db

    async def ensure_table(self) -> None:
        async with self.db.pool.acquire() as conn:
            if self.db.is_sqlite:
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS weekly_briefs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        week_start VARCHAR(20) NOT NULL UNIQUE,
                        payload TEXT NOT NULL,
                        computed_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS daily_briefs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        day VARCHAR(20) NOT NULL UNIQUE,
                        payload TEXT NOT NULL,
                        computed_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            else:
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS weekly_briefs (
                        id SERIAL PRIMARY KEY,
                        week_start VARCHAR(20) NOT NULL UNIQUE,
                        payload TEXT NOT NULL,
                        computed_at TIMESTAMP DEFAULT NOW()
                    )
                    """
                )
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS daily_briefs (
                        id SERIAL PRIMARY KEY,
                        day VARCHAR(20) NOT NULL UNIQUE,
                        payload TEXT NOT NULL,
                        computed_at TIMESTAMP DEFAULT NOW()
                    )
                    """
                )

    async def _merge_topics(
        self, *, window_days: int, trends_limit: int = 10, radar_limit: int = 10, top_n: int = 10
    ) -> Dict[str, Any]:
        from services.idea_radar_service import IdeaRadarService
        from services.trends_service import TrendsService

        # compute() seulement : ne pas ecraser les caches globaux trends/radar (prod Postgres)
        trends_list = await TrendsService(self.db).compute(
            window_days=window_days, limit=trends_limit
        )
        radar_list = await IdeaRadarService(self.db).compute(
            window_days=window_days, limit=radar_limit
        )

        topics: List[Dict[str, Any]] = []
        for t in trends_list or []:
            topics.append(
                {
                    "kind": "trend",
                    "term": t.get("term"),
                    "theme": t.get("kind"),
                    "score": t.get("score"),
                    "article_count": t.get("article_count"),
                    "sample_titles": (t.get("sample_titles") or [])[:3],
                }
            )
        for idea in radar_list or []:
            topics.append(
                {
                    "kind": "radar",
                    "term": idea.get("title") or idea.get("theme"),
                    "theme": idea.get("theme"),
                    "score": idea.get("score"),
                    "article_count": idea.get("article_count"),
                    "sample_titles": (idea.get("sample_titles") or [])[:3],
                    "intents": idea.get("intents") or [],
                }
            )

        topics.sort(key=lambda x: (-float(x.get("score") or 0), -(x.get("article_count") or 0)))
        return {
            "topics": topics[:top_n],
            "trends_count": len(trends_list or []),
            "radar_count": len(radar_list or []),
        }

    async def compute(self, *, week_start: Optional[str] = None) -> Dict[str, Any]:
        ws = week_start or week_start_iso()
        merged = await self._merge_topics(window_days=7, top_n=10)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        return {
            "period": "weekly",
            "week_start": ws,
            "generated_at": now.isoformat(),
            "headline": f"Brief semaine du {ws}",
            **merged,
        }

    async def compute_daily(self, *, day: Optional[str] = None) -> Dict[str, Any]:
        d = day or day_iso()
        # Fenetre 2j pour avoir un peu de signal sans noyer le jour
        merged = await self._merge_topics(window_days=2, trends_limit=8, radar_limit=8, top_n=8)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        return {
            "period": "daily",
            "day": d,
            "generated_at": now.isoformat(),
            "headline": f"Brief du {d}",
            **merged,
        }

    async def refresh(self, *, week_start: Optional[str] = None) -> Dict[str, Any]:
        await self.ensure_table()
        payload = await self.compute(week_start=week_start)
        ws = payload["week_start"]
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        raw = json.dumps(payload, ensure_ascii=False)
        async with self.db.pool.acquire() as conn:
            await conn.execute("DELETE FROM weekly_briefs WHERE week_start = $1", ws)
            await conn.execute(
                """
                INSERT INTO weekly_briefs (week_start, payload, computed_at)
                VALUES ($1, $2, $3)
                """,
                ws,
                raw,
                now,
            )
        payload["computed_at"] = now.isoformat()
        return payload

    async def refresh_daily(self, *, day: Optional[str] = None) -> Dict[str, Any]:
        await self.ensure_table()
        payload = await self.compute_daily(day=day)
        d = payload["day"]
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        raw = json.dumps(payload, ensure_ascii=False)
        async with self.db.pool.acquire() as conn:
            await conn.execute("DELETE FROM daily_briefs WHERE day = $1", d)
            await conn.execute(
                """
                INSERT INTO daily_briefs (day, payload, computed_at)
                VALUES ($1, $2, $3)
                """,
                d,
                raw,
                now,
            )
        payload["computed_at"] = now.isoformat()
        return payload

    def _parse_payload(self, raw: Any) -> Dict[str, Any]:
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            try:
                data = json.loads(raw)
                return data if isinstance(data, dict) else {}
            except json.JSONDecodeError:
                return {}
        return {}

    async def get(self, *, week_start: Optional[str] = None) -> Dict[str, Any]:
        await self.ensure_table()
        ws = week_start or week_start_iso()
        async with self.db.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT week_start, payload, computed_at FROM weekly_briefs WHERE week_start = $1",
                ws,
            )
        if not row:
            return await self.refresh(week_start=ws)
        payload = self._parse_payload(row["payload"])
        ca = row["computed_at"]
        if ca and hasattr(ca, "isoformat"):
            ca = ca.isoformat()
        payload["computed_at"] = ca
        payload["week_start"] = ws
        payload.setdefault("period", "weekly")
        return payload

    async def get_daily(self, *, day: Optional[str] = None, auto: bool = True) -> Dict[str, Any]:
        """Retourne le brief du jour. Si auto=True et manquant/stale → regenerer."""
        await self.ensure_table()
        d = day or day_iso()
        async with self.db.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT day, payload, computed_at FROM daily_briefs WHERE day = $1",
                d,
            )
        if not row:
            return await self.refresh_daily(day=d)

        payload = self._parse_payload(row["payload"])
        ca = row["computed_at"]
        ca_iso = ca.isoformat() if ca and hasattr(ca, "isoformat") else str(ca or "")

        # Auto : si le brief stocke n'est plus "aujourd'hui" (appel avec day force) deja filtre
        # ou s'il a plus de ~18h (session longue), on regenere
        stale = False
        if auto and ca and hasattr(ca, "date"):
            stale = ca.date().isoformat() != d
        elif auto and ca_iso:
            try:
                parsed = datetime.fromisoformat(ca_iso.replace("Z", ""))
                stale = (datetime.now(timezone.utc).replace(tzinfo=None) - parsed) > timedelta(hours=18)
            except ValueError:
                stale = False

        if stale:
            return await self.refresh_daily(day=d)

        payload["computed_at"] = ca_iso
        payload["day"] = d
        payload.setdefault("period", "daily")
        return payload
