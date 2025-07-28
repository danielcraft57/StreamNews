import os
import asyncpg
from typing import List, Dict, Optional
import json

class Database:
    def __init__(self):
        self.database_url = os.getenv("DATABASE_URL", "postgresql://streamnews:streamnews123@postgres:5432/streamnews")
        self.pool = None

    async def init_db(self):
        """Initialise la connexion à la base de données et crée les tables"""
        self.pool = await asyncpg.create_pool(self.database_url)
        
        async with self.pool.acquire() as conn:
            # Création de la table des sites
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS sites (
                    id SERIAL PRIMARY KEY,
                    url VARCHAR(500) NOT NULL,
                    status VARCHAR(50) NOT NULL DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    total_pages_analyzed INTEGER DEFAULT 0,
                    rss_feeds JSONB DEFAULT '[]'::jsonb
                )
            """)
            
            # Création de la table des pages analysées
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS pages (
                    id SERIAL PRIMARY KEY,
                    site_id INTEGER REFERENCES sites(id),
                    url VARCHAR(1000) NOT NULL,
                    title VARCHAR(500),
                    rss_feeds JSONB DEFAULT '[]'::jsonb,
                    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

    async def create_site_analysis(self, url: str, status: str = "pending") -> int:
        """Crée une nouvelle analyse de site"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "INSERT INTO sites (url, status) VALUES ($1, $2) RETURNING id",
                url, status
            )
            return row['id']

    async def update_site_status(self, site_id: int, status: str, rss_feeds: List[Dict] = None, total_pages: int = 0):
        """Met à jour le statut d'un site"""
        async with self.pool.acquire() as conn:
            if rss_feeds is not None:
                await conn.execute(
                    "UPDATE sites SET status = $1, rss_feeds = $2, total_pages_analyzed = $3, updated_at = CURRENT_TIMESTAMP WHERE id = $4",
                    status, json.dumps(rss_feeds), total_pages, site_id
                )
            else:
                await conn.execute(
                    "UPDATE sites SET status = $1, updated_at = CURRENT_TIMESTAMP WHERE id = $2",
                    status, site_id
                )

    async def add_page_analysis(self, site_id: int, url: str, title: str = None, rss_feeds: List[Dict] = None):
        """Ajoute l'analyse d'une page"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO pages (site_id, url, title, rss_feeds) VALUES ($1, $2, $3, $4)",
                site_id, url, title, json.dumps(rss_feeds or [])
            )

    async def get_site(self, site_id: int) -> Optional[Dict]:
        """Récupère les détails d'un site"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM sites WHERE id = $1",
                site_id
            )
            if row:
                return dict(row)
            return None

    async def get_all_sites(self) -> List[Dict]:
        """Récupère tous les sites analysés"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM sites ORDER BY created_at DESC")
            return [dict(row) for row in rows]

    async def get_site_pages(self, site_id: int) -> List[Dict]:
        """Récupère toutes les pages d'un site"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM pages WHERE site_id = $1 ORDER BY analyzed_at DESC",
                site_id
            )
            return [dict(row) for row in rows] 