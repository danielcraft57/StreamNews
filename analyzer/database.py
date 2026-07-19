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
        if 'meta_extra' in data:
            raw = self._parse_json_field(data['meta_extra'])
            data['meta_extra'] = raw if isinstance(raw, dict) else {}
        if 'images' in data:
            raw = self._parse_json_field(data['images'])
            data['images'] = raw if isinstance(raw, list) else []
        if 'article_meta' in data:
            raw = self._parse_json_field(data['article_meta'])
            data['article_meta'] = raw if isinstance(raw, dict) else {}
        # Dates asyncpg -> iso pour le front
        for key in (
            'created_at', 'updated_at', 'analyzed_at', 'published_at',
            'fetched_at', 'enriched_at',
        ):
            if key in data and data[key] is not None and hasattr(data[key], 'isoformat'):
                data[key] = data[key].isoformat()
        return data

    async def init_db(self, reset: bool = False):
        """Initialise la connexion et le schema (pas de migrations).

        reset=True ou STREAMNEWS_RESET_DB=1 : DROP + recreate (pages/articles CASCADE).
        """
        self.pool = await asyncpg.create_pool(self.database_url)
        do_reset = reset or os.getenv("STREAMNEWS_RESET_DB", "").strip() in ("1", "true", "yes")

        async with self.pool.acquire() as conn:
            if do_reset:
                await conn.execute("DROP TABLE IF EXISTS articles CASCADE")
                await conn.execute("DROP TABLE IF EXISTS pages CASCADE")
                await conn.execute("DROP TABLE IF EXISTS sites CASCADE")

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS sites (
                    id SERIAL PRIMARY KEY,
                    url VARCHAR(500) NOT NULL,
                    status VARCHAR(50) NOT NULL DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    total_pages_analyzed INTEGER DEFAULT 0,
                    rss_feeds JSONB DEFAULT '[]'::jsonb,
                    celery_task_id VARCHAR(255),
                    site_title VARCHAR(500),
                    favicon_url VARCHAR(1000),
                    meta_description TEXT,
                    meta_extra JSONB DEFAULT '{}'::jsonb
                )
            """)
            await conn.execute("""
                ALTER TABLE sites
                ADD COLUMN IF NOT EXISTS celery_task_id VARCHAR(255)
            """)
            await conn.execute("""
                ALTER TABLE sites
                ADD COLUMN IF NOT EXISTS site_title VARCHAR(500)
            """)
            await conn.execute("""
                ALTER TABLE sites
                ADD COLUMN IF NOT EXISTS favicon_url VARCHAR(1000)
            """)
            await conn.execute("""
                ALTER TABLE sites
                ADD COLUMN IF NOT EXISTS meta_description TEXT
            """)
            await conn.execute("""
                ALTER TABLE sites
                ADD COLUMN IF NOT EXISTS meta_extra JSONB DEFAULT '{}'::jsonb
            """)

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS pages (
                    id SERIAL PRIMARY KEY,
                    site_id INTEGER NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
                    url VARCHAR(1000) NOT NULL,
                    title VARCHAR(500),
                    rss_feeds JSONB DEFAULT '[]'::jsonb,
                    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS articles (
                    id SERIAL PRIMARY KEY,
                    site_id INTEGER NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
                    feed_url VARCHAR(1000) NOT NULL,
                    title VARCHAR(1000),
                    link VARCHAR(2000) NOT NULL,
                    summary TEXT,
                    author VARCHAR(500),
                    published_at TIMESTAMP,
                    guid VARCHAR(2000),
                    dedupe_key VARCHAR(2100) NOT NULL DEFAULT '',
                    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    content_html TEXT,
                    content_text TEXT,
                    images JSONB DEFAULT '[]'::jsonb,
                    article_meta JSONB DEFAULT '{}'::jsonb,
                    enriched_at TIMESTAMP,
                    enrich_status VARCHAR(50),
                    enrich_error TEXT,
                    UNIQUE (site_id, link)
                )
            """)
            await conn.execute("""
                ALTER TABLE articles
                ADD COLUMN IF NOT EXISTS dedupe_key VARCHAR(2100) NOT NULL DEFAULT ''
            """)
            await conn.execute("""
                ALTER TABLE articles
                ADD COLUMN IF NOT EXISTS content_html TEXT
            """)
            await conn.execute("""
                ALTER TABLE articles
                ADD COLUMN IF NOT EXISTS content_text TEXT
            """)
            await conn.execute("""
                ALTER TABLE articles
                ADD COLUMN IF NOT EXISTS images JSONB DEFAULT '[]'::jsonb
            """)
            await conn.execute("""
                ALTER TABLE articles
                ADD COLUMN IF NOT EXISTS article_meta JSONB DEFAULT '{}'::jsonb
            """)
            await conn.execute("""
                ALTER TABLE articles
                ADD COLUMN IF NOT EXISTS enriched_at TIMESTAMP
            """)
            await conn.execute("""
                ALTER TABLE articles
                ADD COLUMN IF NOT EXISTS enrich_status VARCHAR(50)
            """)
            await conn.execute("""
                ALTER TABLE articles
                ADD COLUMN IF NOT EXISTS enrich_error TEXT
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_articles_site_published
                ON articles (site_id, published_at DESC NULLS LAST)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_articles_enrich_status
                ON articles (site_id, enrich_status)
            """)

            # Installs existantes : forcer ON DELETE CASCADE sans migration
            await conn.execute("""
                DO $$
                BEGIN
                    ALTER TABLE pages DROP CONSTRAINT IF EXISTS pages_site_id_fkey;
                    ALTER TABLE pages
                        ADD CONSTRAINT pages_site_id_fkey
                        FOREIGN KEY (site_id) REFERENCES sites(id) ON DELETE CASCADE;

                    ALTER TABLE articles DROP CONSTRAINT IF EXISTS articles_site_id_fkey;
                    ALTER TABLE articles
                        ADD CONSTRAINT articles_site_id_fkey
                        FOREIGN KEY (site_id) REFERENCES sites(id) ON DELETE CASCADE;
                EXCEPTION WHEN others THEN
                    NULL;
                END $$;
            """)

        # Backfill dedupe une seule fois par process (evite de rescanner a chaque tache)
        if not getattr(self, "_dedupe_ensured", False):
            deleted = await self.ensure_article_dedupe()
            self._dedupe_ensured = True
            if deleted:
                import logging
                logging.getLogger(__name__).info(
                    "Dedupe articles: %s doublons supprimes", deleted
                )

    async def create_site_analysis(self, url: str, status: str = "pending") -> int:
        """Crée une nouvelle analyse de site"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "INSERT INTO sites (url, status) VALUES ($1, $2) RETURNING id",
                url, status
            )
            return row['id']

    async def set_celery_task_id(self, site_id: int, task_id: Optional[str]) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE sites SET celery_task_id = $1, updated_at = CURRENT_TIMESTAMP WHERE id = $2",
                task_id,
                site_id,
            )

    async def is_cancel_requested(self, site_id: int) -> bool:
        async with self.pool.acquire() as conn:
            status = await conn.fetchval(
                "SELECT status FROM sites WHERE id = $1", site_id
            )
            return status in ("cancelled", "cancelling")

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

    async def update_site_meta(self, site_id: int, meta: Dict) -> None:
        """Enregistre titre / favicon / description / meta OG du site."""
        if not meta:
            return
        extra = {
            k: v
            for k, v in meta.items()
            if k in ("og_image", "og_site_name", "theme_color") and v
        }
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE sites SET
                    site_title = COALESCE($2, site_title),
                    favicon_url = COALESCE($3, favicon_url),
                    meta_description = COALESCE($4, meta_description),
                    meta_extra = CASE
                        WHEN $5::jsonb IS NULL THEN meta_extra
                        ELSE COALESCE(meta_extra, '{}'::jsonb) || $5::jsonb
                    END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = $1
                """,
                site_id,
                meta.get("title"),
                meta.get("favicon_url"),
                meta.get("description"),
                json.dumps(extra) if extra else None,
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

    async def delete_site(self, site_id: int) -> Optional[Dict]:
        """Supprime un site ; pages + articles partent via ON DELETE CASCADE.
        Les feeds (JSONB sur sites/pages) disparaissent avec."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                site = await conn.fetchrow("SELECT * FROM sites WHERE id = $1", site_id)
                if not site:
                    return None
                articles = await conn.fetchval(
                    "SELECT COUNT(*) FROM articles WHERE site_id = $1", site_id
                )
                pages = await conn.fetchval(
                    "SELECT COUNT(*) FROM pages WHERE site_id = $1", site_id
                )
                data = self._row_to_dict(site)
                await conn.execute("DELETE FROM sites WHERE id = $1", site_id)
                return {
                    "site": data,
                    "deleted": {
                        "site_id": site_id,
                        "pages": int(pages or 0),
                        "articles": int(articles or 0),
                        "feeds": len(data.get("rss_feeds") or []),
                    },
                }

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
        """Liste articles (sans gros corps HTML - pour le panneau lecteur)."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, site_id, feed_url, title, link, summary, author,
                       published_at, guid, dedupe_key, fetched_at,
                       images, article_meta, enriched_at, enrich_status, enrich_error
                FROM articles
                WHERE site_id = $1
                ORDER BY published_at DESC NULLS LAST, fetched_at DESC
                LIMIT $2
                """,
                site_id,
                limit,
            )
            return [self._row_to_dict(row) for row in rows]

    async def get_article(self, article_id: int) -> Optional[Dict]:
        """Detail d'un article (contenu enrichi inclus)."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM articles WHERE id = $1",
                article_id,
            )
            if row:
                return self._row_to_dict(row)
            return None

    async def list_articles_needing_enrichment(
        self, site_id: int, limit: int = 50
    ) -> List[Dict]:
        """Articles sans enrichissement ok (ou en erreur), pour bulk."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, link, enrich_status
                FROM articles
                WHERE site_id = $1
                  AND (enrich_status IS NULL OR enrich_status NOT IN ('ok', 'pending'))
                ORDER BY published_at DESC NULLS LAST, fetched_at DESC
                LIMIT $2
                """,
                site_id,
                limit,
            )
            return [self._row_to_dict(row) for row in rows]

    async def set_article_enrich_pending(self, article_id: int) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE articles SET
                    enrich_status = 'pending',
                    enrich_error = NULL
                WHERE id = $1
                """,
                article_id,
            )

    async def update_article_enrichment(
        self,
        article_id: int,
        *,
        content_html: Optional[str] = None,
        content_text: Optional[str] = None,
        images: Optional[List[Dict]] = None,
        article_meta: Optional[Dict] = None,
        enrich_status: str = "ok",
        enrich_error: Optional[str] = None,
        title: Optional[str] = None,
        author: Optional[str] = None,
    ) -> None:
        """Persiste le resultat d'enrichissement (ok ou error)."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE articles SET
                    content_html = COALESCE($2, content_html),
                    content_text = COALESCE($3, content_text),
                    images = COALESCE($4::jsonb, images),
                    article_meta = COALESCE($5::jsonb, article_meta),
                    enrich_status = $6,
                    enrich_error = $7,
                    enriched_at = CASE WHEN $6 = 'ok' THEN CURRENT_TIMESTAMP ELSE enriched_at END,
                    title = COALESCE($8, title),
                    author = COALESCE($9, author)
                WHERE id = $1
                """,
                article_id,
                content_html,
                content_text,
                json.dumps(images) if images is not None else None,
                json.dumps(article_meta) if article_meta is not None else None,
                enrich_status,
                enrich_error,
                ((title or "")[:1000] or None) if title is not None else None,
                ((author or "")[:500] or None) if author is not None else None,
            )

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
        """Insert/update un article. Dedup sur dedupe_key (guid ou lien normalise)."""
        from utils import article_dedupe_key, normalize_identifier, normalize_url

        link_n = normalize_url(link)
        if not link_n:
            return False
        guid_n = normalize_identifier(guid)
        key = article_dedupe_key(link_n, guid_n)
        feed_n = normalize_url(feed_url) or (feed_url or "")[:1000]

        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO articles
                    (site_id, feed_url, title, link, summary, author, published_at, guid, dedupe_key)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (site_id, dedupe_key) DO UPDATE SET
                    feed_url = EXCLUDED.feed_url,
                    title = EXCLUDED.title,
                    link = EXCLUDED.link,
                    summary = EXCLUDED.summary,
                    author = EXCLUDED.author,
                    published_at = COALESCE(EXCLUDED.published_at, articles.published_at),
                    guid = COALESCE(EXCLUDED.guid, articles.guid),
                    fetched_at = CURRENT_TIMESTAMP
                """,
                site_id,
                feed_n[:1000],
                (title or "")[:1000] or None,
                link_n[:2000],
                summary,
                (author or "")[:500] or None,
                published_at,
                (guid_n or "")[:2000] or None,
                key[:2100],
            )
            return True

    async def ensure_article_dedupe(self) -> int:
        """Backfill dedupe_key, purge doublons http/https, ajoute UNIQUE."""
        from utils import article_dedupe_key, normalize_identifier, normalize_url
        from collections import defaultdict

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, site_id, link, guid, feed_url FROM articles ORDER BY id"
            )
            groups = defaultdict(list)
            for row in rows:
                link_n = normalize_url(row["link"]) or row["link"]
                guid_n = normalize_identifier(row["guid"])
                key = article_dedupe_key(link_n, guid_n)
                groups[(row["site_id"], key)].append(
                    {
                        "id": row["id"],
                        "link_n": link_n,
                        "guid_n": guid_n,
                        "feed_n": normalize_url(row["feed_url"]) or row["feed_url"],
                        "key": key,
                    }
                )

            deleted = 0
            for (_site_id, _key), items in groups.items():
                keep = items[0]
                for dup in items[1:]:
                    await conn.execute("DELETE FROM articles WHERE id = $1", dup["id"])
                    deleted += 1
                await conn.execute(
                    """
                    UPDATE articles
                    SET dedupe_key = $1,
                        link = $2,
                        guid = COALESCE($3, guid),
                        feed_url = $4
                    WHERE id = $5
                    """,
                    keep["key"][:2100],
                    keep["link_n"][:2000],
                    keep["guid_n"],
                    (keep["feed_n"] or "")[:1000],
                    keep["id"],
                )

            await conn.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint
                        WHERE conname = 'articles_site_id_dedupe_key_key'
                    ) THEN
                        ALTER TABLE articles
                            ADD CONSTRAINT articles_site_id_dedupe_key_key
                            UNIQUE (site_id, dedupe_key);
                    END IF;
                EXCEPTION WHEN others THEN
                    NULL;
                END $$;
            """)
            return deleted

    async def ingest_rss_articles(self, site_id: int, feeds: List[Dict], max_per_feed: int = 50) -> int:
        """Parse chaque flux RSS et stocke les articles. Retourne le nombre upserted."""
        import feedparser
        from datetime import datetime, timezone
        from time import mktime

        feeds = feeds or []
        from utils import collapse_equivalent_feeds

        feeds = collapse_equivalent_feeds(feeds)
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
                if created:
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
 