import os
from typing import List, Dict, Optional, Any
import json

from db_backend import create_pool, is_sqlite_url

# Defaut sans secret : SQLite local. Prod/CI doivent exporter DATABASE_URL.
_DEFAULT_DATABASE_URL = "sqlite:///./data/streamnews.db"


class Database:
    def __init__(self):
        self.database_url = os.getenv("DATABASE_URL", _DEFAULT_DATABASE_URL)
        self.pool = None
        self.backend = "sqlite" if is_sqlite_url(self.database_url) else "postgres"

    @property
    def is_sqlite(self) -> bool:
        return self.backend == "sqlite"

    async def close(self):
        """Ferme le pool (obligatoire sous Celery + aiosqlite avant fin de event loop)."""
        if self.pool is not None:
            await self.pool.close()
            self.pool = None

    async def __aenter__(self):
        await self.init_db()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()
        return False

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

    @staticmethod
    def _merge_image_lists(existing: Any, new: Any, limit: int = 20) -> List[Dict]:
        base = existing if isinstance(existing, list) else []
        incoming = new if isinstance(new, list) else []
        out: List[Dict] = []
        seen = set()
        for img in base + incoming:
            if not isinstance(img, dict):
                continue
            url = img.get("url")
            if not url or url in seen:
                continue
            seen.add(url)
            out.append(img)
            if len(out) >= limit:
                break
        return out

    @staticmethod
    def _merge_article_meta_dict(existing: Any, new: Any) -> Dict[str, Any]:
        base = existing if isinstance(existing, dict) else {}
        incoming = new if isinstance(new, dict) else {}
        out = dict(base)
        for key, val in incoming.items():
            if key == "sources":
                srcs = list(out.get("sources") or [])
                for src in val or []:
                    if src and src not in srcs:
                        srcs.append(src)
                out["sources"] = srcs
            elif key == "keywords":
                kws = list(out.get("keywords") or [])
                seen = {k.lower() for k in kws}
                for kw in val or []:
                    label = str(kw).strip()
                    if label and label.lower() not in seen:
                        seen.add(label.lower())
                        kws.append(label)
                out["keywords"] = kws[:30]
            elif key not in out or out.get(key) in (None, "", []):
                out[key] = val
        return out

    async def init_db(self, reset: bool = False):
        """Initialise la connexion et le schema (pas de migrations).

        reset=True ou STREAMNEWS_RESET_DB=1 : DROP + recreate (pages/articles CASCADE).
        Backend : Postgres (prod) ou SQLite (local) selon DATABASE_URL.
        """
        self.pool = await create_pool(self.database_url)
        self.backend = getattr(self.pool, "backend", self.backend)
        do_reset = reset or os.getenv("STREAMNEWS_RESET_DB", "").strip() in ("1", "true", "yes")

        if self.is_sqlite:
            await self._init_schema_sqlite(do_reset)
        else:
            await self._init_schema_postgres(do_reset)

        # Backfill dedupe une seule fois par process (evite de rescanner a chaque tache)
        if not getattr(self, "_dedupe_ensured", False):
            deleted = await self.ensure_article_dedupe()
            dup_sites = await self.ensure_site_domain_unique()
            self._dedupe_ensured = True
            if deleted or dup_sites:
                import logging
                logging.getLogger(__name__).info(
                    "Dedupe: %s articles, %s sites fusionnes", deleted, dup_sites
                )

    async def _init_schema_sqlite(self, do_reset: bool):
        async with self.pool.acquire() as conn:
            if do_reset:
                await conn.execute("DROP TABLE IF EXISTS articles")
                await conn.execute("DROP TABLE IF EXISTS pages")
                await conn.execute("DROP TABLE IF EXISTS sites")

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS sites (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url VARCHAR(500) NOT NULL,
                    status VARCHAR(50) NOT NULL DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    total_pages_analyzed INTEGER DEFAULT 0,
                    rss_feeds TEXT DEFAULT '[]',
                    celery_task_id VARCHAR(255),
                    site_title VARCHAR(500),
                    favicon_url VARCHAR(1000),
                    meta_description TEXT,
                    meta_extra TEXT DEFAULT '{}',
                    domain VARCHAR(255)
                )
            """)
            for col_sql in (
                "ALTER TABLE sites ADD COLUMN celery_task_id VARCHAR(255)",
                "ALTER TABLE sites ADD COLUMN site_title VARCHAR(500)",
                "ALTER TABLE sites ADD COLUMN favicon_url VARCHAR(1000)",
                "ALTER TABLE sites ADD COLUMN meta_description TEXT",
                "ALTER TABLE sites ADD COLUMN meta_extra TEXT DEFAULT '{}'",
                "ALTER TABLE sites ADD COLUMN domain VARCHAR(255)",
            ):
                try:
                    await conn.execute(col_sql)
                except Exception:
                    pass

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS pages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    site_id INTEGER NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
                    url VARCHAR(1000) NOT NULL,
                    title VARCHAR(500),
                    rss_feeds TEXT DEFAULT '[]',
                    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS articles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                    images TEXT DEFAULT '[]',
                    article_meta TEXT DEFAULT '{}',
                    enriched_at TIMESTAMP,
                    enrich_status VARCHAR(50),
                    enrich_error TEXT,
                    UNIQUE (site_id, link)
                )
            """)
            for col_sql in (
                "ALTER TABLE articles ADD COLUMN dedupe_key VARCHAR(2100) NOT NULL DEFAULT ''",
                "ALTER TABLE articles ADD COLUMN content_html TEXT",
                "ALTER TABLE articles ADD COLUMN content_text TEXT",
                "ALTER TABLE articles ADD COLUMN images TEXT DEFAULT '[]'",
                "ALTER TABLE articles ADD COLUMN article_meta TEXT DEFAULT '{}'",
                "ALTER TABLE articles ADD COLUMN enriched_at TIMESTAMP",
                "ALTER TABLE articles ADD COLUMN enrich_status VARCHAR(50)",
                "ALTER TABLE articles ADD COLUMN enrich_error TEXT",
            ):
                try:
                    await conn.execute(col_sql)
                except Exception:
                    pass

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_articles_site_published
                ON articles (site_id, published_at DESC)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_articles_enrich_status
                ON articles (site_id, enrich_status)
            """)

    async def _init_schema_postgres(self, do_reset: bool):
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
                    meta_extra JSONB DEFAULT '{}'::jsonb,
                    domain VARCHAR(255)
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
                ALTER TABLE sites
                ADD COLUMN IF NOT EXISTS domain VARCHAR(255)
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

    @staticmethod
    def merge_rss_feeds(existing: List[Dict], new: List[Dict]) -> List[Dict]:
        """Ajoute les nouveaux feeds aux existants (dedup URL + equivalents RSS/Atom)."""
        from utils import collapse_equivalent_feeds, normalize_url

        by_url: Dict[str, Dict] = {}
        for feed in list(existing or []) + list(new or []):
            if not isinstance(feed, dict):
                continue
            raw = (feed.get("url") or "").strip()
            if not raw:
                continue
            key = normalize_url(raw) or raw
            prev = by_url.get(key)
            if not prev:
                item = dict(feed)
                item["url"] = key
                by_url[key] = item
                continue
            # Garde le titre / type le plus informatif
            if not prev.get("title") and feed.get("title"):
                prev["title"] = feed["title"]
            if not prev.get("type") and feed.get("type"):
                prev["type"] = feed["type"]
            if not prev.get("source_page") and feed.get("source_page"):
                prev["source_page"] = feed["source_page"]
        merged = list(by_url.values())
        try:
            return collapse_equivalent_feeds(merged)
        except Exception:
            return merged

    async def ensure_site_domain_unique(self) -> int:
        """Backfill domain, fusionne les doublons (ex: 2x BFM), UNIQUE domain."""
        from utils import site_domain
        from collections import defaultdict

        async with self.pool.acquire() as conn:
            try:
                await conn.execute(
                    "ALTER TABLE sites ADD COLUMN IF NOT EXISTS domain VARCHAR(255)"
                )
            except Exception:
                try:
                    await conn.execute(
                        "ALTER TABLE sites ADD COLUMN domain VARCHAR(255)"
                    )
                except Exception:
                    pass
            rows = await conn.fetch(
                "SELECT id, url, domain, rss_feeds FROM sites ORDER BY id ASC"
            )
            groups = defaultdict(list)
            for row in rows:
                domain = (row["domain"] or site_domain(row["url"]) or "").strip() or None
                if domain and domain != row["domain"]:
                    await conn.execute(
                        "UPDATE sites SET domain = $1 WHERE id = $2",
                        domain,
                        row["id"],
                    )
                key = domain or f"__orphan_{row['id']}"
                groups[key].append(
                    {
                        "id": row["id"],
                        "domain": domain,
                        "rss_feeds": self._parse_json_field(row["rss_feeds"]),
                    }
                )

            deleted = 0
            for key, items in groups.items():
                if key.startswith("__orphan_"):
                    continue
                keep = items[0]
                feeds: List[Dict] = []
                for item in items:
                    raw = item.get("rss_feeds") or []
                    if isinstance(raw, list):
                        feeds.extend(raw)
                feeds = self.merge_rss_feeds([], feeds)

                for dup in items[1:]:
                    # Deplace les articles non deja presents sur le site garde
                    await conn.execute(
                        """
                        UPDATE articles AS a
                        SET site_id = $1
                        WHERE a.site_id = $2
                          AND NOT EXISTS (
                            SELECT 1 FROM articles a2
                            WHERE a2.site_id = $1
                              AND a2.dedupe_key = a.dedupe_key
                              AND a.dedupe_key <> ''
                          )
                          AND NOT EXISTS (
                            SELECT 1 FROM articles a2
                            WHERE a2.site_id = $1
                              AND a2.link = a.link
                          )
                        """,
                        keep["id"],
                        dup["id"],
                    )
                    await conn.execute(
                        "DELETE FROM sites WHERE id = $1", dup["id"]
                    )
                    deleted += 1

                await conn.execute(
                    """
                    UPDATE sites
                    SET domain = $1,
                        rss_feeds = $2,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = $3
                    """,
                    keep["domain"] or key,
                    json.dumps(feeds),
                    keep["id"],
                )

            if self.is_sqlite:
                await conn.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS sites_domain_key ON sites(domain)"
                )
            else:
                await conn.execute("""
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM pg_constraint
                            WHERE conname = 'sites_domain_key'
                        ) THEN
                            ALTER TABLE sites
                                ADD CONSTRAINT sites_domain_key UNIQUE (domain);
                        END IF;
                    EXCEPTION WHEN others THEN
                        NULL;
                    END $$;
                """)
            return deleted

    async def get_site_by_domain(self, domain: str) -> Optional[Dict]:
        if not domain:
            return None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM sites WHERE domain = $1", domain
            )
            if row:
                return self._row_to_dict(row)
            return None

    async def upsert_site_for_analysis(
        self, url: str, status: str = "pending"
    ) -> Dict[str, Any]:
        """Cree ou reutilise un site par domaine. Les feeds existants sont conserves."""
        from utils import site_domain

        domain = site_domain(url)
        if not domain:
            raise ValueError("URL invalide (domaine introuvable)")

        async with self.pool.acquire() as conn:
            existing = await conn.fetchrow(
                "SELECT id, celery_task_id, status FROM sites WHERE domain = $1",
                domain,
            )
            if existing:
                await conn.execute(
                    """
                    UPDATE sites SET
                        url = $1,
                        status = $2,
                        celery_task_id = NULL,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = $3
                    """,
                    url[:500],
                    status,
                    existing["id"],
                )
                return {
                    "site_id": existing["id"],
                    "reused": True,
                    "domain": domain,
                    "old_task_id": existing["celery_task_id"],
                    "old_status": existing["status"],
                }

            row = await conn.fetchrow(
                """
                INSERT INTO sites (url, status, domain)
                VALUES ($1, $2, $3)
                RETURNING id
                """,
                url[:500],
                status,
                domain,
            )
            return {
                "site_id": row["id"],
                "reused": False,
                "domain": domain,
                "old_task_id": None,
                "old_status": None,
            }

    async def create_site_analysis(self, url: str, status: str = "pending") -> int:
        """Compat : upsert par domaine, retourne l'id."""
        result = await self.upsert_site_for_analysis(url, status)
        return result["site_id"]

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

    async def update_site_status(
        self,
        site_id: int,
        status: str,
        rss_feeds: List[Dict] = None,
        total_pages: int = 0,
        merge_feeds: bool = True,
    ):
        """Met a jour le statut ; les feeds sont fusionnes avec l'existant par defaut."""
        async with self.pool.acquire() as conn:
            if rss_feeds is not None:
                feeds = rss_feeds
                if merge_feeds:
                    row = await conn.fetchrow(
                        "SELECT rss_feeds FROM sites WHERE id = $1", site_id
                    )
                    existing = (
                        self._parse_json_field(row["rss_feeds"]) if row else []
                    )
                    if not isinstance(existing, list):
                        existing = []
                    feeds = self.merge_rss_feeds(existing, rss_feeds)
                await conn.execute(
                    "UPDATE sites SET status = $1, rss_feeds = $2, total_pages_analyzed = $3, updated_at = CURRENT_TIMESTAMP WHERE id = $4",
                    status, json.dumps(feeds), total_pages, site_id
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
            if self.is_sqlite:
                row = await conn.fetchrow(
                    "SELECT meta_extra FROM sites WHERE id = $1", site_id
                )
                current = self._parse_json_field(row["meta_extra"]) if row else {}
                if not isinstance(current, dict):
                    current = {}
                if extra:
                    current.update(extra)
                await conn.execute(
                    """
                    UPDATE sites SET
                        site_title = COALESCE($2, site_title),
                        favicon_url = COALESCE($3, favicon_url),
                        meta_description = COALESCE($4, meta_description),
                        meta_extra = $5,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = $1
                    """,
                    site_id,
                    meta.get("title"),
                    meta.get("favicon_url"),
                    meta.get("description"),
                    json.dumps(current),
                )
            else:
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
        order = (
            "ORDER BY published_at DESC, fetched_at DESC"
            if self.is_sqlite
            else "ORDER BY published_at DESC NULLS LAST, fetched_at DESC"
        )
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT id, site_id, feed_url, title, link, summary, author,
                       published_at, guid, dedupe_key, fetched_at,
                       images, article_meta, enriched_at, enrich_status, enrich_error
                FROM articles
                WHERE site_id = $1
                {order}
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
        order = (
            "ORDER BY published_at DESC, fetched_at DESC"
            if self.is_sqlite
            else "ORDER BY published_at DESC NULLS LAST, fetched_at DESC"
        )
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT id, link, enrich_status
                FROM articles
                WHERE site_id = $1
                  AND (enrich_status IS NULL OR enrich_status NOT IN ('ok', 'pending'))
                {order}
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
                    images = COALESCE($4, images),
                    article_meta = COALESCE($5, article_meta),
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
        images: Optional[List[Dict]] = None,
        article_meta: Optional[Dict] = None,
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
            existing = await conn.fetchrow(
                """
                SELECT images, article_meta, enrich_status
                FROM articles
                WHERE site_id = $1 AND dedupe_key = $2
                """,
                site_id,
                key[:2100],
            )

            images_json = None
            meta_json = None
            if images is not None or article_meta is not None:
                if existing and existing.get("enrich_status") == "ok":
                    if images is not None:
                        images_json = json.dumps(self._parse_json_field(existing["images"]))
                    if article_meta is not None:
                        meta_json = json.dumps(
                            self._merge_article_meta_dict(
                                self._parse_json_field(existing["article_meta"]), article_meta
                            )
                        )
                elif existing:
                    if images is not None:
                        images_json = json.dumps(
                            self._merge_image_lists(
                                self._parse_json_field(existing["images"]), images
                            )
                        )
                    if article_meta is not None:
                        meta_json = json.dumps(
                            self._merge_article_meta_dict(
                                self._parse_json_field(existing["article_meta"]), article_meta
                            )
                        )
                else:
                    if images is not None:
                        images_json = json.dumps(images)
                    if article_meta is not None:
                        meta_json = json.dumps(article_meta)

            await conn.execute(
                """
                INSERT INTO articles
                    (site_id, feed_url, title, link, summary, author, published_at, guid, dedupe_key,
                     images, article_meta)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, COALESCE($10, '[]'), COALESCE($11, '{}'))
                ON CONFLICT (site_id, dedupe_key) DO UPDATE SET
                    feed_url = EXCLUDED.feed_url,
                    title = EXCLUDED.title,
                    link = EXCLUDED.link,
                    summary = EXCLUDED.summary,
                    author = EXCLUDED.author,
                    published_at = COALESCE(EXCLUDED.published_at, articles.published_at),
                    guid = COALESCE(EXCLUDED.guid, articles.guid),
                    images = CASE WHEN $10 IS NOT NULL THEN $10 ELSE articles.images END,
                    article_meta = CASE WHEN $11 IS NOT NULL THEN $11 ELSE articles.article_meta END,
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
                images_json,
                meta_json,
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

            if self.is_sqlite:
                await conn.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS articles_site_id_dedupe_key_key
                    ON articles (site_id, dedupe_key)
                    """
                )
            else:
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
        from services.ingest_service import IngestService
        from utils import collapse_equivalent_feeds

        feeds = collapse_equivalent_feeds(feeds or [])
        service = IngestService(max_entries=max_per_feed)
        seen_feed_urls = set()
        count = 0

        for feed in feeds:
            feed_url = (feed.get("url") or "").strip()
            if not feed_url or feed_url in seen_feed_urls:
                continue
            seen_feed_urls.add(feed_url)

            for art in service.parse_feed(feed_url):
                ok = await self.upsert_article(
                    site_id=site_id,
                    feed_url=art.feed_url,
                    title=art.title,
                    link=art.link,
                    summary=art.summary,
                    author=art.author,
                    published_at=art.published_at,
                    guid=art.guid,
                    images=art.images or None,
                    article_meta=art.article_meta or None,
                )
                if ok:
                    count += 1

        return count

    async def cleanup_old_analyses(self, days: int = 30) -> int:
        """Supprime les analyses (articles + pages + sites) plus anciennes que N jours."""
        from datetime import datetime, timedelta

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                if self.is_sqlite:
                    cutoff = (datetime.utcnow() - timedelta(days=days)).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                    await conn.execute(
                        """
                        DELETE FROM articles
                        WHERE site_id IN (
                            SELECT id FROM sites WHERE created_at < $1
                        )
                        """,
                        cutoff,
                    )
                    await conn.execute(
                        """
                        DELETE FROM pages
                        WHERE site_id IN (
                            SELECT id FROM sites WHERE created_at < $1
                        )
                        """,
                        cutoff,
                    )
                    result = await conn.execute(
                        "DELETE FROM sites WHERE created_at < $1",
                        cutoff,
                    )
                else:
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
                    return int(str(result).split()[-1])
                except (ValueError, IndexError):
                    return 0 