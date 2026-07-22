"""Radar idees : signaux d'opportunite SaaS/IT depuis les articles."""
from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

# (key, pattern, weight)
INTENT_PATTERNS: List[Tuple[str, re.Pattern[str], float]] = [
    ("id_pay", re.compile(r"\bi'?d\s+pay\b|\bje\s+paier?ais\b|\bwilling\s+to\s+pay\b", re.I), 3.5),
    ("looking_for", re.compile(r"\blooking\s+for\b|\ba\s+la\s+recherche\b|\bcherche\s+un\s+(outil|logiciel|saas)\b", re.I), 3.0),
    ("alternative_to", re.compile(r"\balternative\s+to\b|\balternative\s+[aà]\b|\bremplacer\b|\binstead\s+of\b", re.I), 3.0),
    ("wish_existed", re.compile(r"\bwish\s+(there\s+was|i\s+had)\b|\bsi\s+seulement\b|\bj'?aimerais\s+qu'?il\s+existe\b", re.I), 3.2),
    ("frustrated", re.compile(r"\bfrustrated\s+with\b|\bfed\s+up\b|\bmarre\s+de\b|\bpenible\b|\bpénible\b", re.I), 2.8),
    ("need_tool", re.compile(r"\bbesoin\s+d'?un\s+outil\b|\bneed\s+a\s+(tool|app|saas)\b|\bquelqu'?un\s+connait\b", re.I), 3.0),
    ("build_in_public", re.compile(r"\bbuild\s+in\s+public\b|\bindie\s+hacker\b|\bmrr\b|\bbootstrapp", re.I), 2.2),
    ("launch", re.compile(r"\blaunch(ing|ed)?\b|\blance(r|ment)\b|\bmvp\b|\bproduct\s+hunt\b", re.I), 2.0),
    ("pricing_pain", re.compile(r"\btoo\s+expensive\b|\btrop\s+cher\b|\bpricing\b|\btarif", re.I), 2.4),
]

THEME_KEYWORDS: Dict[str, Sequence[str]] = {
    "saas": ("saas", "b2b", "b2c", "subscription", "abonnement", "software as a service"),
    "devtools": ("devtools", "developer tools", "api", "sdk", "cli", "ide", "github", "gitlab", "ci/cd"),
    "ai": ("ai", "llm", "gpt", "machine learning", "ml ", "rag", "agent ia", "openai", "anthropic"),
    "billing": ("billing", "stripe", "invoicing", "facture", "paiement", "subscription billing"),
    "auth": ("auth", "oauth", "sso", "login", "authentication", "authentification", "passkey"),
    "self-host": ("self-host", "self host", "selfhost", "on-prem", "on prem", "homelab", "docker compose"),
    "open-source": ("open source", "opensource", "open-source", "foss", "mit license", "gpl"),
    "mvp": ("mvp", "minimum viable", "prototype", "poc", "side project"),
    "automation": ("automation", "automatisation", "workflow", "zapier", "n8n", "no-code", "nocode"),
}

THEME_LABELS = {
    "saas": "SaaS / B2B",
    "devtools": "Devtools",
    "ai": "IA / LLM",
    "billing": "Billing",
    "auth": "Auth",
    "self-host": "Self-host",
    "open-source": "Open source",
    "mvp": "MVP / Side project",
    "automation": "Automation",
    "general": "Signal general",
}

INTENT_LABELS = {
    "id_pay": "Pret a payer",
    "looking_for": "Cherche une solution",
    "alternative_to": "Cherche une alternative",
    "wish_existed": "Souhaite que ca existe",
    "frustrated": "Frustration outil",
    "need_tool": "Besoin d'un outil",
    "build_in_public": "Build in public",
    "launch": "Lancement / MVP",
    "pricing_pain": "Douleur pricing",
}


def _norm_blob(*parts: Optional[str]) -> str:
    return " ".join(str(p or "") for p in parts).strip()


def match_intents(text: str) -> List[Tuple[str, float, str]]:
    """Retourne [(key, weight, matched_span), ...]."""
    if not text:
        return []
    out: List[Tuple[str, float, str]] = []
    seen = set()
    for key, pattern, weight in INTENT_PATTERNS:
        m = pattern.search(text)
        if not m or key in seen:
            continue
        seen.add(key)
        out.append((key, weight, m.group(0)[:80]))
    return out


def match_themes(text: str) -> List[str]:
    if not text:
        return []
    low = text.lower()
    found = []
    for theme, kws in THEME_KEYWORDS.items():
        for kw in kws:
            if kw.lower() in low:
                found.append(theme)
                break
    return found


def snippet_around(text: str, needle: str, radius: int = 70) -> str:
    if not text:
        return ""
    low = text.lower()
    idx = low.find((needle or "").lower())
    if idx < 0:
        return (text[: radius * 2] + ("…" if len(text) > radius * 2 else "")).strip()
    start = max(0, idx - radius)
    end = min(len(text), idx + len(needle) + radius)
    chunk = text[start:end].strip()
    if start > 0:
        chunk = "…" + chunk
    if end < len(text):
        chunk = chunk + "…"
    return chunk.replace("\n", " ")[:220]


def score_bucket(
    *,
    intent_weight: float,
    intent_hits: int,
    article_count: int,
    site_count: int,
    recency_bonus: float,
) -> float:
    """Score opportunite (v1 deterministe)."""
    diversity = 1.0 + 0.25 * max(0, site_count - 1)
    volume = 1.0 + 0.12 * max(0, article_count - 1)
    intent_part = float(intent_weight) + (0.4 * max(0, intent_hits - 1))
    theme_bonus = 1.5 if intent_hits else 0.8
    return round((intent_part + theme_bonus) * volume * diversity + recency_bonus, 2)


class IdeaRadarService:
    def __init__(self, db):
        self.db = db

    async def ensure_table(self) -> None:
        async with self.db.pool.acquire() as conn:
            if self.db.is_sqlite:
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS radar_ideas (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        theme VARCHAR(80) NOT NULL,
                        title VARCHAR(500) NOT NULL,
                        score REAL NOT NULL DEFAULT 0,
                        intent_count INTEGER NOT NULL DEFAULT 0,
                        article_count INTEGER NOT NULL DEFAULT 0,
                        window_days INTEGER NOT NULL DEFAULT 30,
                        sample_titles TEXT,
                        sample_snippets TEXT,
                        evidence_ids TEXT,
                        intents TEXT,
                        computed_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                await conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_radar_window_score ON radar_ideas(window_days, score)"
                )
                await conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_radar_theme ON radar_ideas(theme)"
                )
            else:
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS radar_ideas (
                        id SERIAL PRIMARY KEY,
                        theme VARCHAR(80) NOT NULL,
                        title VARCHAR(500) NOT NULL,
                        score DOUBLE PRECISION NOT NULL DEFAULT 0,
                        intent_count INTEGER NOT NULL DEFAULT 0,
                        article_count INTEGER NOT NULL DEFAULT 0,
                        window_days INTEGER NOT NULL DEFAULT 30,
                        sample_titles TEXT,
                        sample_snippets TEXT,
                        evidence_ids TEXT,
                        intents TEXT,
                        computed_at TIMESTAMP DEFAULT NOW()
                    )
                    """
                )
                await conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_radar_window_score ON radar_ideas(window_days, score)"
                )
                await conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_radar_theme ON radar_ideas(theme)"
                )

    async def compute(
        self,
        *,
        window_days: int = 30,
        limit: int = 40,
    ) -> List[Dict[str, Any]]:
        window_days = max(1, min(int(window_days or 30), 365))
        limit = max(1, min(int(limit or 40), 100))
        since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=window_days)
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        async with self.db.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, site_id, title, summary, content_text,
                       COALESCE(fetched_at, published_at) AS seen_at
                FROM articles
                WHERE COALESCE(fetched_at, published_at) >= $1
                ORDER BY COALESCE(fetched_at, published_at) DESC
                LIMIT 2000
                """,
                since,
            )

        buckets: Dict[str, Dict[str, Any]] = {}

        def ensure(theme: str) -> Dict[str, Any]:
            item = buckets.get(theme)
            if not item:
                item = {
                    "theme": theme,
                    "title": THEME_LABELS.get(theme, theme),
                    "article_ids": set(),
                    "site_ids": set(),
                    "intent_keys": set(),
                    "intent_weight": 0.0,
                    "titles": [],
                    "snippets": [],
                    "recency_bonus": 0.0,
                }
                buckets[theme] = item
            return item

        for row in rows:
            blob = _norm_blob(row["title"], row["summary"], row["content_text"])
            if len(blob) < 8:
                continue
            intents = match_intents(blob)
            themes = match_themes(blob)
            if not intents and not themes:
                continue
            if not themes:
                themes = ["general"]
            # Skip pure theme noise without intent for "general" — keep themed without intent lightly
            aid = int(row["id"])
            sid = row["site_id"]
            title = (row["title"] or "")[:120]
            seen_at = row["seen_at"]
            age_days = 0.0
            if seen_at:
                try:
                    if hasattr(seen_at, "timestamp"):
                        age_days = max(0.0, (now - seen_at.replace(tzinfo=None)).total_seconds() / 86400.0)
                    else:
                        age_days = 0.0
                except Exception:
                    age_days = 0.0
            recency = max(0.0, 2.0 - (age_days / max(1.0, window_days)) * 2.0)

            for theme in themes:
                # Require intent for general; themed cards can appear with weaker score
                if theme == "general" and not intents:
                    continue
                item = ensure(theme)
                if aid not in item["article_ids"]:
                    item["article_ids"].add(aid)
                    if title and len(item["titles"]) < 4:
                        item["titles"].append(title)
                    if sid is not None:
                        item["site_ids"].add(int(sid))
                item["recency_bonus"] = max(item["recency_bonus"], recency)
                for key, weight, span in intents:
                    if key not in item["intent_keys"]:
                        item["intent_keys"].add(key)
                        item["intent_weight"] += weight
                        if len(item["snippets"]) < 4:
                            item["snippets"].append(snippet_around(blob, span))
                if intents and len(item["snippets"]) < 4 and not any(
                    snippet_around(blob, intents[0][2]) == s for s in item["snippets"]
                ):
                    pass

        scored: List[Dict[str, Any]] = []
        for item in buckets.values():
            count = len(item["article_ids"])
            if count < 1:
                continue
            intent_hits = len(item["intent_keys"])
            # Drop theme-only with a single weak article and no intent
            if intent_hits == 0 and count < 2:
                continue
            score = score_bucket(
                intent_weight=item["intent_weight"] or (1.0 if intent_hits == 0 else 0.0),
                intent_hits=intent_hits or (1 if item["intent_weight"] else 0),
                article_count=count,
                site_count=len(item["site_ids"]),
                recency_bonus=item["recency_bonus"],
            )
            if intent_hits == 0:
                score = round(score * 0.55, 2)
            intents_list = sorted(item["intent_keys"])
            label = THEME_LABELS.get(item["theme"], item["theme"])
            if intents_list:
                top = INTENT_LABELS.get(intents_list[0], intents_list[0])
                label = f"{label} · {top}"
            scored.append(
                {
                    "theme": item["theme"],
                    "title": label[:500],
                    "score": score,
                    "intent_count": intent_hits,
                    "article_count": count,
                    "window_days": window_days,
                    "sample_titles": item["titles"],
                    "sample_snippets": item["snippets"],
                    "evidence_ids": sorted(item["article_ids"])[:20],
                    "intents": intents_list,
                }
            )

        scored.sort(key=lambda x: (-x["score"], -x["article_count"], x["theme"]))
        return scored[:limit]

    async def refresh(self, *, window_days: int = 30, limit: int = 40) -> Dict[str, Any]:
        await self.ensure_table()
        ideas = await self.compute(window_days=window_days, limit=limit)
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        async with self.db.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM radar_ideas WHERE window_days = $1",
                window_days,
            )
            for idea in ideas:
                await conn.execute(
                    """
                    INSERT INTO radar_ideas (
                        theme, title, score, intent_count, article_count, window_days,
                        sample_titles, sample_snippets, evidence_ids, intents, computed_at
                    ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
                    """,
                    idea["theme"],
                    idea["title"],
                    float(idea["score"]),
                    int(idea["intent_count"]),
                    int(idea["article_count"]),
                    int(window_days),
                    json.dumps(idea.get("sample_titles") or [], ensure_ascii=False),
                    json.dumps(idea.get("sample_snippets") or [], ensure_ascii=False),
                    json.dumps(idea.get("evidence_ids") or [], ensure_ascii=False),
                    json.dumps(idea.get("intents") or [], ensure_ascii=False),
                    now,
                )

        return {
            "window_days": window_days,
            "count": len(ideas),
            "computed_at": now.isoformat(),
            "ideas": ideas,
        }

    async def list_stored(
        self,
        *,
        window_days: int = 30,
        theme: Optional[str] = None,
        limit: int = 40,
    ) -> Dict[str, Any]:
        await self.ensure_table()
        window_days = max(1, min(int(window_days or 30), 365))
        limit = max(1, min(int(limit or 40), 100))

        async with self.db.pool.acquire() as conn:
            clauses = ["window_days = $1"]
            args: List[Any] = [window_days]
            if theme and theme != "all":
                args.append(theme)
                clauses.append(f"theme = ${len(args)}")
            args.append(limit)
            sql = f"""
                SELECT theme, title, score, intent_count, article_count, window_days,
                       sample_titles, sample_snippets, evidence_ids, intents, computed_at
                FROM radar_ideas
                WHERE {' AND '.join(clauses)}
                ORDER BY score DESC, article_count DESC
                LIMIT ${len(args)}
            """
            rows = await conn.fetch(sql, *args)

        ideas = []
        computed_at = None
        for row in rows:
            def _loads(raw):
                if isinstance(raw, str):
                    try:
                        return json.loads(raw)
                    except json.JSONDecodeError:
                        return []
                return raw if isinstance(raw, list) else []

            ca = row["computed_at"]
            if ca and hasattr(ca, "isoformat"):
                ca = ca.isoformat()
                computed_at = computed_at or ca
            ideas.append(
                {
                    "theme": row["theme"],
                    "title": row["title"],
                    "score": float(row["score"] or 0),
                    "intent_count": int(row["intent_count"] or 0),
                    "article_count": int(row["article_count"] or 0),
                    "window_days": int(row["window_days"] or window_days),
                    "sample_titles": _loads(row["sample_titles"]),
                    "sample_snippets": _loads(row["sample_snippets"]),
                    "evidence_ids": _loads(row["evidence_ids"]),
                    "intents": _loads(row["intents"]),
                    "computed_at": ca,
                }
            )

        return {
            "window_days": window_days,
            "theme": theme or "all",
            "count": len(ideas),
            "computed_at": computed_at,
            "ideas": ideas,
        }
