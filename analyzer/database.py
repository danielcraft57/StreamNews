import os
import asyncpg
from typing import List, Dict, Optional, Any
import json

class Database:
    def __init__(self):
        self.database_url = os.getenv("DATABASE_URL", "postgresql://streamnews:streamnews123@localhost:5432/streamnews")
        self.pool = None

    @staticmethod
    def _parse_json_field(value: Any):
        """asyncpg renvoie souvent le JSONB en str : on normalise en objet Python."""
        if value is None:
            return []
        if isinstance(value, (list, dict)):
            return value
        if isinstance(value, (bytes, bytearray)):
            value = value.decode()
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return []
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return []
        return value

    def _row_to_dict(self, row) -> Dict:
        data = dict(row)
        if 'rss_feeds' in data:
            data['rss_feeds'] = self._parse_json_field(data['rss_feeds'])
        # Dates asyncpg -> iso pour le front
        for key in ('created_at', 'updated_at', 'analyzed_at', 'published_at', 'fetched_at'):
            if key in data and data[key] is not None and hasattr(data[key], 'isoformat'):
                data[key] = data[key].isoformat()
        return data

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

            # Articles extraits des flux RSS
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS articles (
                    id SERIAL PRIMARY KEY,
                    site_id INTEGER REFERENCES sites(id) ON DELETE CASCADE,
                    feed_url VARCHAR(1000) NOT NULL,
                    title VARCHAR(1000),
                    link VARCHAR(2000) NOT NULL,
                    summary TEXT,
                    author VARCHAR(500),
                    published_at TIMESTAMP,
                    guid VARCHAR(2000),
                    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (site_id, link)
                )
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_articles_site_published
                ON articles (site_id, published_at DESC NULLS LAST)
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
                    "UPDATE sites SET status = $1, rss_feeds = $2::jsonb, total_pages_analyzed = $3, updated_at = CURRENT_TIMESTAMP WHERE id = $4",
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
                "INSERT INTO pages (site_id, url, title, rss_feeds) VALUES ($1, $2, $3, $4::jsonb)",
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
                return self._row_to_dict(row)
            return None

    async def get_all_sites(self) -> List[Dict]:
        """Récupère tous les sites analysés"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM sites ORDER BY created_at DESC")
            return [self._row_to_dict(row) for row in rows]

    async def get_site_pages(self, site_id: int) -> List[Dict]:
        """Récupère toutes les pages d'un site"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM pages WHERE site_id = $1 ORDER BY analyzed_at DESC",
                site_id
            )
            return [self._row_to_dict(row) for row in rows]

    async def get_site_articles(self, site_id: int, limit: int = 100) -> List[Dict]:
        """Récupère les articles RSS d'un site (plus récents d'abord)."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM articles
                WHERE site_id = $1
                ORDER BY published_at DESC NULLS LAST, fetched_at DESC
                LIMIT $2
                """,
                site_id,
                limit,
            )
            return [self._row_to_dict(row) for row in rows]

    async def upsert_article(
        self,
        site_id: int,
        feed_url: str,
        title: str,
        link: str,
        summary: str = None,
        author: str = None,
        published_at=None,
        guid: str = None,
    ) -> bool:
        """Insert ou ignore un article (dedup sur site_id+link). Retourne True si cree."""
        if not link:
            return False
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO articles
                    (site_id, feed_url, title, link, summary, author, published_at, guid)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (site_id, link) DO UPDATE SET
                    title = EXCLUDED.title,
                    summary = EXCLUDED.summary,
                    author = EXCLUDED.author,
                    published_at = COALESCE(EXCLUDED.published_at, articles.published_at),
                    guid = COALESCE(EXCLUDED.guid, articles.guid),
                    fetched_at = CURRENT_TIMESTAMP
                """,
                site_id,
                feed_url[:1000],
                (title or "")[:1000] or None,
                link[:2000],
                summary,
                (author or "")[:500] or None,
                published_at,
                (guid or "")[:2000] or None,
            )
            return True

    async def ingest_rss_articles(self, site_id: int, feeds: List[Dict], max_per_feed: int = 50) -> int:
        """Parse chaque flux RSS et stocke les articles. Retourne le nombre upserted."""
        import feedparser
        from datetime import datetime, timezone
        from time import mktime

        feeds = feeds or []
        seen_feed_urls = set()
        count = 0

        for feed in feeds:
            feed_url = (feed.get("url") or "").strip()
            if not feed_url or feed_url in seen_feed_urls:
                continue
            seen_feed_urls.add(feed_url)

            try:
                parsed = feedparser.parse(feed_url)
            except Exception:
                continue

            for entry in (parsed.entries or [])[:max_per_feed]:
                link = entry.get("link") or entry.get("id") or ""
                if not link:
                    continue

                published_at = None
                published_parsed = entry.get("published_parsed") or entry.get("updated_parsed")
                if published_parsed:
                    try:
                        published_at = datetime.fromtimestamp(mktime(published_parsed), tz=timezone.utc).replace(tzinfo=None)
                    except (OverflowError, ValueError, TypeError):
                        published_at = None

                summary = entry.get("summary") or entry.get("description") or ""
                if len(summary) > 4000:
                    summary = summary[:4000] + "…"

                created = await self.upsert_article(
                    site_id=site_id,
                    feed_url=feed_url,
                    title=entry.get("title") or "Sans titre",
                    link=link,
                    summary=summary or None,
                    author=entry.get("author"),
                    published_at=published_at,
                    guid=entry.get("id") or entry.get("guid"),
                )
                count += 1

        return count

    async def cleanup_old_analyses(self, days: int = 30) -> int:
        """Supprime les analyses (articles + pages + sites) plus anciennes que N jours."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    DELETE FROM articles
                    WHERE site_id IN (
                        SELECT id FROM sites
                        WHERE created_at < NOW() - make_interval(days => $1)
                    )
                    """,
                    days,
                )
                await conn.execute(
                    """
                    DELETE FROM pages
                    WHERE site_id IN (
                        SELECT id FROM sites
                        WHERE created_at < NOW() - make_interval(days => $1)
                    )
                    """,
                    days,
                )
                result = await conn.execute(
                    """
                    DELETE FROM sites
                    WHERE created_at < NOW() - make_interval(days => $1)
                    """,
                    days,
                )
                try:
                    return int(result.split()[-1])
                except (ValueError, IndexError):
                    return 0
 