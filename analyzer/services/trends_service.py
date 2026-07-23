"""Calcul et persistence des tendances a partir des articles / NLP."""
from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

STOPWORDS = {
    "a", "au", "aux", "avec", "ce", "ces", "dans", "de", "des", "du", "en", "et",
    "je", "la", "le", "les", "un", "une", "par", "pour", "sur", "the", "and", "or",
    "of", "to", "in", "on", "for", "news", "article", "articles", "http", "https",
    "www", "com", "fr", "non", "oui", "plus", "moins", "tout", "tous", "cette",
    "son", "sa", "ses", "nos", "vos", "leur", "leurs", "qui", "que", "quoi",
    "accueil", "ressources",
}

NOISE_RE = re.compile(r"^[\W\d_]+$", re.UNICODE)


def _norm_term(raw: str) -> str:
    t = re.sub(r"\s+", " ", str(raw or "").strip().lower())
    return t[:200]


def _is_useful(term: str) -> bool:
    if not term or len(term) < 3:
        return False
    if term in STOPWORDS:
        return False
    if NOISE_RE.match(term):
        return False
    # ignore pure numbers / years alone
    if term.isdigit() and len(term) <= 4:
        return False
    return True


class TrendsService:
    def __init__(self, db):
        self.db = db

    async def ensure_table(self) -> None:
        async with self.db.pool.acquire() as conn:
            if self.db.is_sqlite:
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS trends (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        term VARCHAR(500) NOT NULL,
                        kind VARCHAR(50) NOT NULL DEFAULT 'keyword',
                        label VARCHAR(50),
                        score REAL NOT NULL DEFAULT 0,
                        article_count INTEGER NOT NULL DEFAULT 0,
                        window_days INTEGER NOT NULL DEFAULT 7,
                        site_id INTEGER,
                        computed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        sample_titles TEXT
                    )
                    """
                )
                await conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_trends_window_score ON trends(window_days, score)"
                )
                await conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_trends_term ON trends(term)"
                )
            else:
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS trends (
                        id SERIAL PRIMARY KEY,
                        term VARCHAR(500) NOT NULL,
                        kind VARCHAR(50) NOT NULL DEFAULT 'keyword',
                        label VARCHAR(50),
                        score DOUBLE PRECISION NOT NULL DEFAULT 0,
                        article_count INTEGER NOT NULL DEFAULT 0,
                        window_days INTEGER NOT NULL DEFAULT 7,
                        site_id INTEGER,
                        computed_at TIMESTAMP DEFAULT NOW(),
                        sample_titles TEXT
                    )
                    """
                )
                await conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_trends_window_score ON trends(window_days, score)"
                )
                await conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_trends_term ON trends(term)"
                )

    async def compute(
        self,
        *,
        window_days: int = 7,
        site_id: Optional[int] = None,
        site_ids: Optional[List[int]] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        window_days = max(1, min(int(window_days or 7), 365))
        limit = max(1, min(int(limit or 50), 100))
        since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=window_days)

        filter_ids: Optional[List[int]] = None
        if site_ids is not None:
            filter_ids = [int(x) for x in site_ids if x is not None]
            if not filter_ids:
                return []
        elif site_id is not None:
            filter_ids = [int(site_id)]

        buckets: Dict[Tuple[str, str, Optional[str]], Dict[str, Any]] = {}

        def bump(term: str, kind: str, label: Optional[str], article_id: int, title: str, weight: float = 1.0):
            key = (term, kind, label)
            item = buckets.get(key)
            if not item:
                item = {
                    "term": term,
                    "kind": kind,
                    "label": label,
                    "article_ids": set(),
                    "titles": [],
                    "weight": 0.0,
                }
                buckets[key] = item
            if article_id not in item["article_ids"]:
                item["article_ids"].add(article_id)
                if title and len(item["titles"]) < 3:
                    item["titles"].append(title[:120])
            item["weight"] += weight

        async def _fetch(conn, sql_all: str, sql_in: str):
            if filter_ids is None:
                return await conn.fetch(sql_all, since)
            placeholders = ", ".join(f"${i + 2}" for i in range(len(filter_ids)))
            return await conn.fetch(sql_in.format(placeholders=placeholders), since, *filter_ids)

        async with self.db.pool.acquire() as conn:
            rows = await _fetch(
                conn,
                """
                SELECT ak.keyword, a.id AS article_id, a.title
                FROM article_keywords ak
                JOIN articles a ON a.id = ak.article_id
                WHERE COALESCE(a.fetched_at, a.published_at) >= $1
                """,
                """
                SELECT ak.keyword, a.id AS article_id, a.title
                FROM article_keywords ak
                JOIN articles a ON a.id = ak.article_id
                WHERE COALESCE(a.fetched_at, a.published_at) >= $1
                  AND a.site_id IN ({placeholders})
                """,
            )
            for row in rows:
                term = _norm_term(row["keyword"])
                if _is_useful(term):
                    bump(term, "keyword", None, int(row["article_id"]), row["title"] or "", 1.0)

            erows = await _fetch(
                conn,
                """
                SELECT ae.text, ae.label, a.id AS article_id, a.title
                FROM article_entities ae
                JOIN articles a ON a.id = ae.article_id
                WHERE COALESCE(a.fetched_at, a.published_at) >= $1
                """,
                """
                SELECT ae.text, ae.label, a.id AS article_id, a.title
                FROM article_entities ae
                JOIN articles a ON a.id = ae.article_id
                WHERE COALESCE(a.fetched_at, a.published_at) >= $1
                  AND a.site_id IN ({placeholders})
                """,
            )
            for row in erows:
                term = _norm_term(row["text"])
                if _is_useful(term):
                    bump(term, "entity", row["label"], int(row["article_id"]), row["title"] or "", 1.4)

            yrows = await _fetch(
                conn,
                """
                SELECT aa.result, a.id AS article_id, a.title
                FROM article_analyses aa
                JOIN articles a ON a.id = aa.article_id
                WHERE aa.tool_name = 'keywords_yake'
                  AND aa.status = 'ok'
                  AND COALESCE(a.fetched_at, a.published_at) >= $1
                """,
                """
                SELECT aa.result, a.id AS article_id, a.title
                FROM article_analyses aa
                JOIN articles a ON a.id = aa.article_id
                WHERE aa.tool_name = 'keywords_yake'
                  AND aa.status = 'ok'
                  AND COALESCE(a.fetched_at, a.published_at) >= $1
                  AND a.site_id IN ({placeholders})
                """,
            )
            for row in yrows:
                result = row["result"]
                if isinstance(result, str):
                    try:
                        result = json.loads(result)
                    except json.JSONDecodeError:
                        result = {}
                kws = (result or {}).get("keywords") if isinstance(result, dict) else None
                if not isinstance(kws, list):
                    continue
                for kw in kws:
                    if isinstance(kw, dict):
                        raw = kw.get("keyword") or kw.get("term") or kw.get("name") or ""
                    else:
                        raw = kw
                    term = _norm_term(raw)
                    if _is_useful(term):
                        bump(term, "yake", None, int(row["article_id"]), row["title"] or "", 1.2)

        scored: List[Dict[str, Any]] = []
        for item in buckets.values():
            count = len(item["article_ids"])
            if count < 1:
                continue
            score = round(float(item["weight"]) * (1.0 + 0.15 * max(0, count - 1)), 2)
            scored.append(
                {
                    "term": item["term"],
                    "kind": item["kind"],
                    "label": item["label"],
                    "score": score,
                    "article_count": count,
                    "window_days": window_days,
                    "site_id": site_id if site_ids is None else None,
                    "sample_titles": item["titles"],
                }
            )

        scored.sort(key=lambda x: (-x["score"], -x["article_count"], x["term"]))
        return scored[:limit]

    async def refresh(
        self,
        *,
        window_days: int = 7,
        site_id: Optional[int] = None,
        site_ids: Optional[List[int]] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        await self.ensure_table()
        trends = await self.compute(
            window_days=window_days, site_id=site_id, site_ids=site_ids, limit=limit
        )
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # Filtre collection : calcul live, ne pas ecraser le cache global
        if site_ids is not None:
            return {
                "window_days": window_days,
                "site_id": None,
                "site_ids": [int(x) for x in site_ids if x is not None],
                "count": len(trends),
                "computed_at": now.isoformat(),
                "trends": trends,
                "persisted": False,
            }

        async with self.db.pool.acquire() as conn:
            if site_id is None:
                await conn.execute(
                    "DELETE FROM trends WHERE window_days = $1 AND site_id IS NULL",
                    window_days,
                )
            else:
                await conn.execute(
                    "DELETE FROM trends WHERE window_days = $1 AND site_id = $2",
                    window_days,
                    site_id,
                )
            for t in trends:
                titles = json.dumps(t.get("sample_titles") or [], ensure_ascii=False)
                await conn.execute(
                    """
                    INSERT INTO trends (
                        term, kind, label, score, article_count, window_days,
                        site_id, computed_at, sample_titles
                    ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
                    """,
                    t["term"],
                    t["kind"],
                    t.get("label"),
                    float(t["score"]),
                    int(t["article_count"]),
                    int(window_days),
                    site_id,
                    now,
                    titles,
                )

        return {
            "window_days": window_days,
            "site_id": site_id,
            "count": len(trends),
            "computed_at": now.isoformat(),
            "trends": trends,
            "persisted": True,
        }

    async def list_stored(
        self,
        *,
        window_days: int = 7,
        site_id: Optional[int] = None,
        kind: Optional[str] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        await self.ensure_table()
        window_days = max(1, min(int(window_days or 7), 365))
        limit = max(1, min(int(limit or 50), 100))

        async with self.db.pool.acquire() as conn:
            clauses = ["window_days = $1"]
            args: List[Any] = [window_days]
            if site_id is None:
                clauses.append("site_id IS NULL")
            else:
                args.append(site_id)
                clauses.append(f"site_id = ${len(args)}")
            if kind and kind != "all":
                args.append(kind)
                clauses.append(f"kind = ${len(args)}")
            args.append(limit)
            sql = f"""
                SELECT term, kind, label, score, article_count, window_days,
                       site_id, computed_at, sample_titles
                FROM trends
                WHERE {' AND '.join(clauses)}
                ORDER BY score DESC, article_count DESC
                LIMIT ${len(args)}
            """
            rows = await conn.fetch(sql, *args)

        trends = []
        computed_at = None
        for row in rows:
            titles = row["sample_titles"]
            if isinstance(titles, str):
                try:
                    titles = json.loads(titles)
                except json.JSONDecodeError:
                    titles = []
            ca = row["computed_at"]
            if ca and hasattr(ca, "isoformat"):
                ca = ca.isoformat()
                computed_at = computed_at or ca
            trends.append(
                {
                    "term": row["term"],
                    "kind": row["kind"],
                    "label": row["label"],
                    "score": float(row["score"] or 0),
                    "article_count": int(row["article_count"] or 0),
                    "window_days": int(row["window_days"] or window_days),
                    "site_id": row["site_id"],
                    "sample_titles": titles if isinstance(titles, list) else [],
                    "computed_at": ca,
                }
            )

        return {
            "window_days": window_days,
            "site_id": site_id,
            "kind": kind or "all",
            "count": len(trends),
            "computed_at": computed_at,
            "trends": trends,
        }
