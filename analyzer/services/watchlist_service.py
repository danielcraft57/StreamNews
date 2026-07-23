"""Watchlist concurrents : mots-cles surveilles + alertes de hausse."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

DEFAULT_KEYWORDS = [
    "billing",
    "auth",
    "rag",
    "self-host",
    "oauth",
    "pricing",
    "llm",
    "sso",
    "webhook",
]


class WatchlistService:
    def __init__(self, db):
        self.db = db

    async def ensure_tables(self) -> None:
        async with self.db.pool.acquire() as conn:
            if self.db.is_sqlite:
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS watch_keywords (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        keyword VARCHAR(200) NOT NULL UNIQUE,
                        active INTEGER NOT NULL DEFAULT 1,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS watch_alerts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        keyword VARCHAR(200) NOT NULL,
                        score REAL NOT NULL DEFAULT 0,
                        delta REAL NOT NULL DEFAULT 0,
                        current_count INTEGER NOT NULL DEFAULT 0,
                        previous_count INTEGER NOT NULL DEFAULT 0,
                        window_days INTEGER NOT NULL DEFAULT 7,
                        sample_titles TEXT,
                        computed_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            else:
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS watch_keywords (
                        id SERIAL PRIMARY KEY,
                        keyword VARCHAR(200) NOT NULL UNIQUE,
                        active BOOLEAN NOT NULL DEFAULT TRUE,
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                    """
                )
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS watch_alerts (
                        id SERIAL PRIMARY KEY,
                        keyword VARCHAR(200) NOT NULL,
                        score DOUBLE PRECISION NOT NULL DEFAULT 0,
                        delta DOUBLE PRECISION NOT NULL DEFAULT 0,
                        current_count INTEGER NOT NULL DEFAULT 0,
                        previous_count INTEGER NOT NULL DEFAULT 0,
                        window_days INTEGER NOT NULL DEFAULT 7,
                        sample_titles TEXT,
                        computed_at TIMESTAMP DEFAULT NOW()
                    )
                    """
                )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_watch_alerts_score ON watch_alerts(window_days, score)"
            )

    async def seed_defaults(self) -> None:
        await self.ensure_tables()
        async with self.db.pool.acquire() as conn:
            for kw in DEFAULT_KEYWORDS:
                existing = await conn.fetchrow(
                    "SELECT id FROM watch_keywords WHERE lower(keyword) = lower($1)",
                    kw,
                )
                if not existing:
                    await conn.execute(
                        "INSERT INTO watch_keywords (keyword, active) VALUES ($1, $2)",
                        kw,
                        True,
                    )

    async def list_keywords(self) -> List[Dict[str, Any]]:
        await self.seed_defaults()
        async with self.db.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, keyword, active, created_at FROM watch_keywords ORDER BY keyword"
            )
        out = []
        for r in rows:
            ca = r["created_at"]
            if ca and hasattr(ca, "isoformat"):
                ca = ca.isoformat()
            out.append(
                {
                    "id": int(r["id"]),
                    "keyword": r["keyword"],
                    "active": bool(r["active"]),
                    "created_at": ca,
                }
            )
        return out

    async def add_keyword(self, keyword: str) -> Dict[str, Any]:
        await self.ensure_tables()
        kw = " ".join(str(keyword or "").strip().lower().split())[:200]
        if len(kw) < 2:
            raise ValueError("Mot-cle trop court")
        async with self.db.pool.acquire() as conn:
            existing = await conn.fetchrow(
                "SELECT id, keyword, active, created_at FROM watch_keywords WHERE lower(keyword) = lower($1)",
                kw,
            )
            if existing:
                await conn.execute(
                    "UPDATE watch_keywords SET active = $1 WHERE id = $2",
                    True,
                    int(existing["id"]),
                )
                return {
                    "id": int(existing["id"]),
                    "keyword": existing["keyword"],
                    "active": True,
                }
            await conn.execute(
                "INSERT INTO watch_keywords (keyword, active) VALUES ($1, $2)",
                kw,
                True,
            )
            row = await conn.fetchrow(
                "SELECT id, keyword, active FROM watch_keywords WHERE lower(keyword) = lower($1)",
                kw,
            )
        return {"id": int(row["id"]), "keyword": row["keyword"], "active": True}

    async def delete_keyword(self, keyword_id: int) -> bool:
        await self.ensure_tables()
        async with self.db.pool.acquire() as conn:
            await conn.execute("DELETE FROM watch_keywords WHERE id = $1", keyword_id)
        return True

    async def _count_keyword(
        self, conn, keyword: str, since, until=None
    ) -> tuple[int, List[str]]:
        like = f"%{keyword}%"
        if until is None:
            rows = await conn.fetch(
                """
                SELECT title FROM articles
                WHERE COALESCE(fetched_at, published_at) >= $1
                  AND (
                    lower(COALESCE(title,'')) LIKE lower($2)
                    OR lower(COALESCE(summary,'')) LIKE lower($2)
                    OR lower(COALESCE(content_text,'')) LIKE lower($2)
                  )
                ORDER BY COALESCE(fetched_at, published_at) DESC
                LIMIT 40
                """,
                since,
                like,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT title FROM articles
                WHERE COALESCE(fetched_at, published_at) >= $1
                  AND COALESCE(fetched_at, published_at) < $2
                  AND (
                    lower(COALESCE(title,'')) LIKE lower($3)
                    OR lower(COALESCE(summary,'')) LIKE lower($3)
                    OR lower(COALESCE(content_text,'')) LIKE lower($3)
                  )
                ORDER BY COALESCE(fetched_at, published_at) DESC
                LIMIT 40
                """,
                since,
                until,
                like,
            )
        titles = [(r["title"] or "")[:120] for r in rows if r["title"]]
        return len(rows), titles[:3]

    async def refresh(self, *, window_days: int = 7) -> Dict[str, Any]:
        await self.seed_defaults()
        window_days = max(1, min(int(window_days or 7), 90))
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        current_since = now - timedelta(days=window_days)
        previous_since = now - timedelta(days=window_days * 2)

        keywords = await self.list_keywords()
        active = [k for k in keywords if k.get("active")]
        alerts: List[Dict[str, Any]] = []

        async with self.db.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM watch_alerts WHERE window_days = $1", window_days
            )
            for item in active:
                kw = item["keyword"]
                cur_n, titles = await self._count_keyword(conn, kw, current_since)
                prev_n, _ = await self._count_keyword(
                    conn, kw, previous_since, until=current_since
                )
                delta = float(cur_n - prev_n)
                # score: volume + hausse relative
                growth = delta / max(1.0, float(prev_n)) if prev_n or cur_n else 0.0
                score = round(cur_n * 1.0 + max(0.0, delta) * 1.5 + max(0.0, growth) * 2.0, 2)
                if cur_n <= 0 and delta <= 0:
                    continue
                payload = {
                    "keyword": kw,
                    "score": score,
                    "delta": delta,
                    "current_count": cur_n,
                    "previous_count": prev_n,
                    "window_days": window_days,
                    "sample_titles": titles,
                }
                await conn.execute(
                    """
                    INSERT INTO watch_alerts (
                        keyword, score, delta, current_count, previous_count,
                        window_days, sample_titles, computed_at
                    ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                    """,
                    kw,
                    score,
                    delta,
                    cur_n,
                    prev_n,
                    window_days,
                    json.dumps(titles, ensure_ascii=False),
                    now,
                )
                alerts.append(payload)

        alerts.sort(key=lambda a: (-a["score"], -a["delta"], a["keyword"]))
        return {
            "window_days": window_days,
            "count": len(alerts),
            "computed_at": now.isoformat(),
            "alerts": alerts,
        }

    async def list_alerts(
        self, *, window_days: int = 7, limit: int = 40
    ) -> Dict[str, Any]:
        await self.ensure_tables()
        window_days = max(1, min(int(window_days or 7), 90))
        limit = max(1, min(int(limit or 40), 100))
        async with self.db.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT keyword, score, delta, current_count, previous_count,
                       window_days, sample_titles, computed_at
                FROM watch_alerts
                WHERE window_days = $1
                ORDER BY score DESC, delta DESC
                LIMIT $2
                """,
                window_days,
                limit,
            )
        if not rows:
            return await self.refresh(window_days=window_days)

        alerts = []
        computed_at = None
        for r in rows:
            titles = r["sample_titles"]
            if isinstance(titles, str):
                try:
                    titles = json.loads(titles)
                except json.JSONDecodeError:
                    titles = []
            ca = r["computed_at"]
            if ca and hasattr(ca, "isoformat"):
                ca = ca.isoformat()
                computed_at = computed_at or ca
            alerts.append(
                {
                    "keyword": r["keyword"],
                    "score": float(r["score"] or 0),
                    "delta": float(r["delta"] or 0),
                    "current_count": int(r["current_count"] or 0),
                    "previous_count": int(r["previous_count"] or 0),
                    "window_days": int(r["window_days"] or window_days),
                    "sample_titles": titles if isinstance(titles, list) else [],
                    "computed_at": ca,
                }
            )
        return {
            "window_days": window_days,
            "count": len(alerts),
            "computed_at": computed_at,
            "alerts": alerts,
        }
