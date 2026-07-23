"""Fiches idee : notes opportunite + export markdown."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def render_idea_markdown(note: Dict[str, Any]) -> str:
    title = note.get("title") or "Idee"
    theme = note.get("theme") or ""
    problem = note.get("problem") or ""
    mvp = note.get("mvp_plan") or ""
    evidence = note.get("evidence") or []
    if isinstance(evidence, str):
        try:
            evidence = json.loads(evidence)
        except json.JSONDecodeError:
            evidence = [evidence] if evidence else []
    refs = note.get("source_refs") or []
    if isinstance(refs, str):
        try:
            refs = json.loads(refs)
        except json.JSONDecodeError:
            refs = []

    lines = [
        f"# {title}",
        "",
        f"**Theme:** {theme}" if theme else "",
        f"**Status:** {note.get('status') or 'draft'}",
        "",
        "## Probleme",
        problem or "_A definir_",
        "",
        "## Preuves",
    ]
    if evidence:
        for e in evidence:
            lines.append(f"- {e}")
    else:
        lines.append("_Aucune preuve pour l'instant_")
    lines.extend(["", "## MVP (2 semaines)", mvp or "_A definir_", "", "## Sources"])
    if refs:
        for r in refs:
            if isinstance(r, dict):
                lines.append(f"- {r.get('title') or r.get('url') or r}")
            else:
                lines.append(f"- {r}")
    else:
        lines.append("_Aucune source_")
    lines.append("")
    return "\n".join([ln for ln in lines if ln is not None])


class IdeaNotesService:
    def __init__(self, db):
        self.db = db

    async def ensure_table(self) -> None:
        async with self.db.pool.acquire() as conn:
            if self.db.is_sqlite:
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS idea_notes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title VARCHAR(500) NOT NULL,
                        theme VARCHAR(80),
                        problem TEXT,
                        evidence TEXT,
                        mvp_plan TEXT,
                        source_refs TEXT,
                        status VARCHAR(40) NOT NULL DEFAULT 'draft',
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            else:
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS idea_notes (
                        id SERIAL PRIMARY KEY,
                        title VARCHAR(500) NOT NULL,
                        theme VARCHAR(80),
                        problem TEXT,
                        evidence TEXT,
                        mvp_plan TEXT,
                        source_refs TEXT,
                        status VARCHAR(40) NOT NULL DEFAULT 'draft',
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP DEFAULT NOW()
                    )
                    """
                )

    def _row_to_dict(self, row) -> Dict[str, Any]:
        def loads(raw, default):
            if raw is None:
                return default
            if isinstance(raw, (list, dict)):
                return raw
            if isinstance(raw, str):
                try:
                    return json.loads(raw)
                except json.JSONDecodeError:
                    return default
            return default

        ca = row["created_at"]
        ua = row["updated_at"]
        if ca and hasattr(ca, "isoformat"):
            ca = ca.isoformat()
        if ua and hasattr(ua, "isoformat"):
            ua = ua.isoformat()
        return {
            "id": int(row["id"]),
            "title": row["title"],
            "theme": row["theme"],
            "problem": row["problem"] or "",
            "evidence": loads(row["evidence"], []),
            "mvp_plan": row["mvp_plan"] or "",
            "source_refs": loads(row["source_refs"], []),
            "status": row["status"] or "draft",
            "created_at": ca,
            "updated_at": ua,
        }

    async def list_notes(self, *, limit: int = 50) -> List[Dict[str, Any]]:
        await self.ensure_table()
        limit = max(1, min(int(limit or 50), 200))
        async with self.db.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM idea_notes
                ORDER BY updated_at DESC, id DESC
                LIMIT $1
                """,
                limit,
            )
        return [self._row_to_dict(r) for r in rows]

    async def get(self, note_id: int) -> Optional[Dict[str, Any]]:
        await self.ensure_table()
        async with self.db.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM idea_notes WHERE id = $1", note_id)
        return self._row_to_dict(row) if row else None

    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        await self.ensure_table()
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        title = str(data.get("title") or "Nouvelle idee").strip()[:500]
        theme = (data.get("theme") or None)
        if theme:
            theme = str(theme)[:80]
        problem = data.get("problem") or ""
        mvp = data.get("mvp_plan") or ""
        evidence = data.get("evidence") or []
        refs = data.get("source_refs") or []
        status = str(data.get("status") or "draft")[:40]
        async with self.db.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO idea_notes (
                    title, theme, problem, evidence, mvp_plan, source_refs,
                    status, created_at, updated_at
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
                """,
                title,
                theme,
                problem,
                json.dumps(evidence, ensure_ascii=False),
                mvp,
                json.dumps(refs, ensure_ascii=False),
                status,
                now,
                now,
            )
            row = await conn.fetchrow(
                "SELECT * FROM idea_notes ORDER BY id DESC LIMIT 1"
            )
        return self._row_to_dict(row)

    async def update(self, note_id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        await self.ensure_table()
        current = await self.get(note_id)
        if not current:
            return None
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        title = str(data.get("title", current["title"])).strip()[:500]
        theme = data.get("theme", current.get("theme"))
        if theme is not None:
            theme = str(theme)[:80] if theme else None
        problem = data.get("problem", current.get("problem") or "")
        mvp = data.get("mvp_plan", current.get("mvp_plan") or "")
        evidence = data.get("evidence", current.get("evidence") or [])
        refs = data.get("source_refs", current.get("source_refs") or [])
        status = str(data.get("status", current.get("status") or "draft"))[:40]
        async with self.db.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE idea_notes SET
                    title=$1, theme=$2, problem=$3, evidence=$4, mvp_plan=$5,
                    source_refs=$6, status=$7, updated_at=$8
                WHERE id=$9
                """,
                title,
                theme,
                problem,
                json.dumps(evidence, ensure_ascii=False),
                mvp,
                json.dumps(refs, ensure_ascii=False),
                status,
                now,
                note_id,
            )
        return await self.get(note_id)

    async def delete(self, note_id: int) -> bool:
        await self.ensure_table()
        async with self.db.pool.acquire() as conn:
            await conn.execute("DELETE FROM idea_notes WHERE id = $1", note_id)
        return True

    async def from_radar(self, idea: Dict[str, Any]) -> Dict[str, Any]:
        theme = idea.get("theme") or "general"
        title = idea.get("title") or THEME_FALLBACK.get(theme, theme)
        titles = idea.get("sample_titles") or []
        snippets = idea.get("sample_snippets") or []
        evidence = list(snippets[:4]) or list(titles[:4])
        intents = idea.get("intents") or []
        problem = (
            f"Signal radar sur « {theme} » "
            f"({idea.get('article_count') or 0} articles, score {idea.get('score') or 0})."
        )
        if intents:
            problem += f" Intents: {', '.join(intents)}."
        mvp = (
            "Semaine 1: valider le probleme avec 5 utilisateurs cibles + landing landing.\n"
            "Semaine 2: MVP minimal (1 flux critique) + pricing hypothese."
        )
        return await self.create(
            {
                "title": title,
                "theme": theme,
                "problem": problem,
                "evidence": evidence,
                "mvp_plan": mvp,
                "source_refs": [{"title": t} for t in titles[:5]],
                "status": "draft",
            }
        )


THEME_FALLBACK = {
    "saas": "Idee SaaS",
    "devtools": "Idee Devtools",
    "ai": "Idee IA",
    "general": "Idee",
}
