"""Collections thematiques de sources."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

DEFAULT_COLLECTIONS = [
    ("devtools", "Devtools", "Outils developpeur, API, CI/CD"),
    ("b2b-saas", "B2B SaaS", "Produits SaaS B2B et pricing"),
    ("ai-infra", "AI infra", "LLM, RAG, agents, infra IA"),
    ("nocode", "No-code", "Automation, no-code, workflows"),
]


class CollectionsService:
    def __init__(self, db):
        self.db = db

    async def ensure_tables(self) -> None:
        async with self.db.pool.acquire() as conn:
            if self.db.is_sqlite:
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS collections (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        slug VARCHAR(80) NOT NULL UNIQUE,
                        name VARCHAR(200) NOT NULL,
                        description TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS collection_sites (
                        collection_id INTEGER NOT NULL,
                        site_id INTEGER NOT NULL,
                        PRIMARY KEY (collection_id, site_id)
                    )
                    """
                )
            else:
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS collections (
                        id SERIAL PRIMARY KEY,
                        slug VARCHAR(80) NOT NULL UNIQUE,
                        name VARCHAR(200) NOT NULL,
                        description TEXT,
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                    """
                )
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS collection_sites (
                        collection_id INTEGER NOT NULL,
                        site_id INTEGER NOT NULL,
                        PRIMARY KEY (collection_id, site_id)
                    )
                    """
                )

    async def seed_defaults(self) -> None:
        await self.ensure_tables()
        async with self.db.pool.acquire() as conn:
            for slug, name, desc in DEFAULT_COLLECTIONS:
                row = await conn.fetchrow(
                    "SELECT id FROM collections WHERE slug = $1", slug
                )
                if not row:
                    await conn.execute(
                        "INSERT INTO collections (slug, name, description) VALUES ($1,$2,$3)",
                        slug,
                        name,
                        desc,
                    )

    async def list_collections(self) -> List[Dict[str, Any]]:
        await self.seed_defaults()
        async with self.db.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT c.id, c.slug, c.name, c.description, c.created_at,
                       (SELECT COUNT(*) FROM collection_sites cs WHERE cs.collection_id = c.id) AS site_count
                FROM collections c
                ORDER BY c.name
                """
            )
        out = []
        for r in rows:
            ca = r["created_at"]
            if ca and hasattr(ca, "isoformat"):
                ca = ca.isoformat()
            out.append(
                {
                    "id": int(r["id"]),
                    "slug": r["slug"],
                    "name": r["name"],
                    "description": r["description"],
                    "site_count": int(r["site_count"] or 0),
                    "created_at": ca,
                }
            )
        return out

    async def get_site_ids(self, collection_id: int) -> List[int]:
        await self.ensure_tables()
        async with self.db.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT site_id FROM collection_sites WHERE collection_id = $1",
                collection_id,
            )
        return [int(r["site_id"]) for r in rows]

    async def get_collection(self, collection_id: int) -> Optional[Dict[str, Any]]:
        await self.ensure_tables()
        async with self.db.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, slug, name, description FROM collections WHERE id = $1",
                collection_id,
            )
            if not row:
                return None
            site_rows = await conn.fetch(
                """
                SELECT s.id, s.url, s.site_title, s.status, s.favicon_url
                FROM collection_sites cs
                JOIN sites s ON s.id = cs.site_id
                WHERE cs.collection_id = $1
                ORDER BY s.id DESC
                """,
                collection_id,
            )
        sites = [
            {
                "id": int(s["id"]),
                "url": s["url"],
                "site_title": s["site_title"],
                "status": s["status"],
                "favicon_url": s["favicon_url"],
            }
            for s in site_rows
        ]
        return {
            "id": int(row["id"]),
            "slug": row["slug"],
            "name": row["name"],
            "description": row["description"],
            "sites": sites,
            "site_ids": [s["id"] for s in sites],
            "site_count": len(sites),
        }

    async def add_site(self, collection_id: int, site_id: int) -> Dict[str, Any]:
        await self.ensure_tables()
        async with self.db.pool.acquire() as conn:
            col = await conn.fetchrow(
                "SELECT id FROM collections WHERE id = $1", collection_id
            )
            if not col:
                raise ValueError("Collection introuvable")
            site = await conn.fetchrow("SELECT id FROM sites WHERE id = $1", site_id)
            if not site:
                raise ValueError("Site introuvable")
            existing = await conn.fetchrow(
                "SELECT 1 FROM collection_sites WHERE collection_id = $1 AND site_id = $2",
                collection_id,
                site_id,
            )
            if not existing:
                await conn.execute(
                    "INSERT INTO collection_sites (collection_id, site_id) VALUES ($1,$2)",
                    collection_id,
                    site_id,
                )
        detail = await self.get_collection(collection_id)
        return detail or {"id": collection_id, "sites": []}

    async def remove_site(self, collection_id: int, site_id: int) -> Dict[str, Any]:
        await self.ensure_tables()
        async with self.db.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM collection_sites WHERE collection_id = $1 AND site_id = $2",
                collection_id,
                site_id,
            )
        detail = await self.get_collection(collection_id)
        return detail or {"id": collection_id, "sites": []}
