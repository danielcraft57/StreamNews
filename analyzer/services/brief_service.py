"""Brief hebdo : top tendances + radar pour la semaine."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional


def week_start_iso(dt: Optional[datetime] = None) -> str:
    now = dt or datetime.now(timezone.utc).replace(tzinfo=None)
    monday = now - timedelta(days=now.weekday())
    return monday.date().isoformat()


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

    async def compute(self, *, week_start: Optional[str] = None) -> Dict[str, Any]:
        from services.idea_radar_service import IdeaRadarService
        from services.trends_service import TrendsService

        ws = week_start or week_start_iso()
        trends_svc = TrendsService(self.db)
        radar_svc = IdeaRadarService(self.db)

        trends_data = await trends_svc.refresh(window_days=7, limit=10)
        radar_data = await radar_svc.refresh(window_days=7, limit=10)

        topics: List[Dict[str, Any]] = []
        for t in trends_data.get("trends") or []:
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
        for idea in radar_data.get("ideas") or []:
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
        top = topics[:10]
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        payload = {
            "week_start": ws,
            "generated_at": now.isoformat(),
            "headline": f"Brief semaine du {ws}",
            "topics": top,
            "trends_count": len(trends_data.get("trends") or []),
            "radar_count": len(radar_data.get("ideas") or []),
        }
        return payload

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
        payload = row["payload"]
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                payload = {}
        ca = row["computed_at"]
        if ca and hasattr(ca, "isoformat"):
            ca = ca.isoformat()
        if isinstance(payload, dict):
            payload["computed_at"] = ca
            payload["week_start"] = ws
        return payload if isinstance(payload, dict) else await self.refresh(week_start=ws)
