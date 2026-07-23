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
        if 'meta_extra' in data:
            raw = self._parse_json_field(data['meta_extra'])
            data['meta_extra'] = raw if isinstance(raw, dict) else {}
        # API shape : hydrate depuis tables normalisees (pas de blob JSON)
        data.setdefault('images', [])
        data.setdefault('article_meta', {})
        data.setdefault('rss_feeds', [])
        # Dates asyncpg -> iso pour le front
        for key in (
            'created_at', 'updated_at', 'analyzed_at', 'published_at',
            'fetched_at', 'enriched_at',
        ):
            if key in data and data[key] is not None and hasattr(data[key], 'isoformat'):
                data[key] = data[key].isoformat()
        if data.get("analysis_status") and isinstance(data.get("article_meta"), dict):
            data["article_meta"].setdefault("analysis_status", data["analysis_status"])
            if data.get("analysis_error"):
                data["article_meta"].setdefault("analysis_error", data["analysis_error"])
            if data.get("analyzed_at"):
                data["article_meta"].setdefault("analyzed_at", data["analyzed_at"])
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
            elif key == "analysis":
                merged_analysis = dict(out.get("analysis") or {})
                for tool_name, block in (val or {}).items():
                    if isinstance(block, dict):
                        merged_analysis[tool_name] = block
                out["analysis"] = merged_analysis
            elif key not in out or out.get(key) in (None, "", []):
                out[key] = val
        return out

    async def init_db(self, reset: bool = False):
        """Initialise la connexion, migrations Alembic et backfill dedupe.

        reset=True ou STREAMNEWS_RESET_DB=1 : downgrade base + upgrade head.
        Backend : Postgres (prod) ou SQLite (local) selon DATABASE_URL.
        """
        do_reset = reset or os.getenv("STREAMNEWS_RESET_DB", "").strip() in ("1", "true", "yes")

        from migrate import run_migrations, _sync_database_url
        import asyncio

        skip_migrate = (
            self.is_sqlite
            and not do_reset
            and os.getenv("STREAMNEWS_SKIP_MIGRATE", "").strip() not in ("0", "false", "no")
        )
        if skip_migrate:
            # Local Windows : alembic sous uvicorn peut rester bloque indefiniment.
            # Si alembic_version existe, on considere la base a jour.
            try:
                import sqlite3
                from pathlib import Path
                from urllib.parse import unquote

                sync_url = _sync_database_url(self.database_url)
                raw = sync_url.replace("sqlite:///", "", 1).split("?")[0]
                db_path = Path(unquote(raw))
                if db_path.is_file():
                    con = sqlite3.connect(str(db_path), timeout=5)
                    try:
                        row = con.execute(
                            "SELECT version_num FROM alembic_version LIMIT 1"
                        ).fetchone()
                    finally:
                        con.close()
                    if row:
                        skip_migrate = True
                    else:
                        skip_migrate = False
                else:
                    skip_migrate = False
            except Exception:
                skip_migrate = False

        if not skip_migrate:
            await asyncio.to_thread(
                lambda: run_migrations(self.database_url, reset=do_reset)
            )

        self.pool = await create_pool(self.database_url)
        self.backend = getattr(self.pool, "backend", self.backend)

        if not getattr(self, "_dedupe_ensured", False):
            deleted = await self.ensure_article_dedupe()
            dup_sites = 0
            # Sur SQLite local ce backfill peut bloquer aiosqlite (ALTER / sync feeds).
            # Les domaines sont deja en place apres migrations ; on saute au startup.
            if not self.is_sqlite:
                try:
                    import asyncio
                    dup_sites = await asyncio.wait_for(
                        self.ensure_site_domain_unique(),
                        timeout=20.0,
                    )
                except Exception as exc:
                    import logging
                    logging.getLogger(__name__).warning(
                        "ensure_site_domain_unique ignoree au startup: %s", exc
                    )
            self._dedupe_ensured = True
            if deleted or dup_sites:
                import logging
                logging.getLogger(__name__).info(
                    "Dedupe: %s articles, %s sites fusionnes", deleted, dup_sites
                )

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
            # SQLite ne comprend pas toujours "ADD COLUMN IF NOT EXISTS"
            if self.is_sqlite:
                try:
                    cols = await conn.fetch("PRAGMA table_info(sites)")
                    names = {r["name"] for r in cols}
                    if "domain" not in names:
                        await conn.execute(
                            "ALTER TABLE sites ADD COLUMN domain VARCHAR(255)"
                        )
                except Exception:
                    pass
            else:
                try:
                    await conn.execute(
                        "ALTER TABLE sites ADD COLUMN IF NOT EXISTS domain VARCHAR(255)"
                    )
                except Exception:
                    pass
            rows = await conn.fetch(
                "SELECT id, url, domain FROM sites ORDER BY id ASC"
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
                    }
                )

            deleted = 0
            from repositories.normalized_sync import sync_rss_feeds_list
            from repositories.normalized_read import load_site_rss_feeds

            for key, items in groups.items():
                if key.startswith("__orphan_"):
                    continue
                keep = items[0]
                feeds: List[Dict] = []
                for item in items:
                    raw = await load_site_rss_feeds(conn, int(item["id"]))
                    feeds.extend(raw)
                feeds = self.merge_rss_feeds([], feeds)

                for dup in items[1:]:
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
                        """
                        UPDATE rss_feeds SET site_id = $1
                        WHERE site_id = $2
                          AND NOT EXISTS (
                            SELECT 1 FROM rss_feeds r2
                            WHERE r2.site_id = $1 AND r2.url = rss_feeds.url
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
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = $2
                    """,
                    keep["domain"] or key,
                    keep["id"],
                )
                await sync_rss_feeds_list(
                    conn,
                    is_sqlite=self.is_sqlite,
                    site_id=int(keep["id"]),
                    feeds=feeds,
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
                    from repositories.normalized_read import load_site_rss_feeds

                    existing = await load_site_rss_feeds(conn, site_id)
                    feeds = self.merge_rss_feeds(existing, rss_feeds)
                await conn.execute(
                    "UPDATE sites SET status = $1, total_pages_analyzed = $2, updated_at = CURRENT_TIMESTAMP WHERE id = $3",
                    status, total_pages, site_id
                )
                from repositories.normalized_sync import sync_rss_feeds_list

                await sync_rss_feeds_list(
                    conn,
                    is_sqlite=self.is_sqlite,
                    site_id=site_id,
                    feeds=feeds,
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
        """Ajoute ou met a jour une page (unique site_id+url) ; feeds -> rss_feeds."""
        async with self.pool.acquire() as conn:
            if self.is_sqlite:
                await conn.execute(
                    """
                    INSERT INTO pages (site_id, url, title)
                    VALUES ($1, $2, $3)
                    ON CONFLICT(site_id, url) DO UPDATE SET
                        title = excluded.title,
                        analyzed_at = CURRENT_TIMESTAMP
                    """,
                    site_id,
                    url,
                    title,
                )
            else:
                await conn.execute(
                    """
                    INSERT INTO pages (site_id, url, title)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (site_id, url) DO UPDATE SET
                        title = EXCLUDED.title,
                        analyzed_at = CURRENT_TIMESTAMP
                    """,
                    site_id,
                    url,
                    title,
                )
            from repositories.normalized_sync import sync_rss_feeds_list

            page = await conn.fetchrow(
                "SELECT id FROM pages WHERE site_id = $1 AND url = $2 ORDER BY id DESC LIMIT 1",
                site_id,
                url,
            )
            page_id = int(page["id"]) if page else None
            await sync_rss_feeds_list(
                conn,
                is_sqlite=self.is_sqlite,
                site_id=site_id,
                feeds=rss_feeds or [],
                source_page_id=page_id,
            )

    async def get_site(self, site_id: int) -> Optional[Dict]:
        """Récupère les détails d'un site"""
        from repositories.sites_repo import SitesRepository

        site = await SitesRepository(self.pool, is_sqlite=self.is_sqlite).get_by_id(site_id)
        return site.to_api_dict() if site else None

    async def delete_site(self, site_id: int) -> Optional[Dict]:
        """Supprime un site ; pages + articles partent via ON DELETE CASCADE."""
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
                from repositories.sites_repo import SitesRepository

                record = await SitesRepository(
                    self.pool, is_sqlite=self.is_sqlite
                ).get_by_id(site_id)
                data = record.to_api_dict() if record else self._row_to_dict(site)
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
        from repositories.sites_repo import SitesRepository

        sites = await SitesRepository(self.pool, is_sqlite=self.is_sqlite).list_all()
        return [s.to_api_dict() for s in sites]

    async def get_site_pages(self, site_id: int) -> List[Dict]:
        """Récupère toutes les pages d'un site"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM pages WHERE site_id = $1 ORDER BY analyzed_at DESC",
                site_id
            )
            pages = [self._row_to_dict(row) for row in rows]
            from repositories.normalized_read import hydrate_pages_batch

            return await hydrate_pages_batch(conn, pages, is_sqlite=self.is_sqlite)

    async def get_site_articles(self, site_id: int, limit: int = 100) -> List[Dict]:
        """Liste articles (sans gros corps HTML - pour le panneau lecteur)."""
        from repositories.articles_repo import ArticlesRepository

        articles = await ArticlesRepository(
            self.pool, is_sqlite=self.is_sqlite
        ).list_by_site(site_id, limit=limit, with_body=False)
        return [a.to_api_dict() for a in articles]

    async def search_articles(
        self,
        query: str,
        *,
        site_id: Optional[int] = None,
        limit: int = 40,
    ) -> List[Dict]:
        from repositories.articles_repo import ArticlesRepository

        articles = await ArticlesRepository(
            self.pool, is_sqlite=self.is_sqlite
        ).search(query, site_id=site_id, limit=limit)
        return [a.to_api_dict() for a in articles]

    async def get_article(self, article_id: int) -> Optional[Dict]:
        """Detail d'un article (contenu enrichi inclus)."""
        from repositories.articles_repo import ArticlesRepository

        article = await ArticlesRepository(
            self.pool, is_sqlite=self.is_sqlite
        ).get_by_id(article_id)
        return article.to_api_dict() if article else None

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

    async def list_articles_needing_analysis(
        self, site_id: int, limit: int = 50
    ) -> List[Dict]:
        """Articles enrichis sans analyse texte ok (colonne analysis_status)."""
        order = (
            "ORDER BY enriched_at DESC, fetched_at DESC"
            if self.is_sqlite
            else "ORDER BY enriched_at DESC NULLS LAST, fetched_at DESC"
        )
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT id, link, enrich_status, analysis_status
                FROM articles
                WHERE site_id = $1
                  AND enrich_status = 'ok'
                  AND COALESCE(content_text, '') != ''
                  AND (
                    analysis_status IS NULL
                    OR analysis_status NOT IN ('ok', 'pending')
                  )
                {order}
                LIMIT $2
                """,
                site_id,
                limit,
            )
            return [self._row_to_dict(row) for row in rows]

    async def set_article_analysis_pending(self, article_id: int) -> None:
        """Colonne analysis_status = source de verite (JSON legacy allégé)."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE articles SET
                    analysis_status = 'pending',
                    analysis_error = NULL
                WHERE id = $1
                """,
                article_id,
            )

    async def update_article_analysis(
        self,
        article_id: int,
        *,
        analysis: Optional[Dict] = None,
        analysis_status: str = "ok",
        analysis_error: Optional[str] = None,
        analyzed_at: Optional[str] = None,
    ) -> None:
        """Persiste l'analyse dans colonnes + article_analyses (pas le blob JSON)."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE articles SET
                    analysis_status = $2,
                    analysis_error = $3,
                    analyzed_at = COALESCE($4, analyzed_at)
                WHERE id = $1
                """,
                article_id,
                analysis_status,
                analysis_error,
                analyzed_at,
            )
            from repositories.normalized_sync import (
                has_normalized_tables,
                sync_article_analyses,
            )

            if analysis is not None and await has_normalized_tables(
                conn, is_sqlite=self.is_sqlite
            ):
                await sync_article_analyses(
                    conn,
                    is_sqlite=self.is_sqlite,
                    article_id=article_id,
                    analysis=analysis,
                )

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
        videos: Optional[List[Dict]] = None,
        audios: Optional[List[Dict]] = None,
        article_meta: Optional[Dict] = None,
        enrich_status: str = "ok",
        enrich_error: Optional[str] = None,
        title: Optional[str] = None,
        author: Optional[str] = None,
    ) -> None:
        """Persiste l'enrichissement ; media/meta -> tables normalisees."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE articles SET
                    content_html = COALESCE($2, content_html),
                    content_text = COALESCE($3, content_text),
                    enrich_status = $4,
                    enrich_error = $5,
                    enriched_at = CASE WHEN $8 = 'ok' THEN CURRENT_TIMESTAMP ELSE enriched_at END,
                    title = COALESCE($6, title),
                    author = COALESCE($7, author)
                WHERE id = $1
                """,
                article_id,
                content_html,
                content_text,
                enrich_status,
                enrich_error,
                ((title or "")[:1000] or None) if title is not None else None,
                ((author or "")[:500] or None) if author is not None else None,
                enrich_status,
            )
            from repositories.normalized_sync import sync_article_after_enrichment

            if (
                images is not None
                or videos is not None
                or audios is not None
                or article_meta is not None
            ):
                await sync_article_after_enrichment(
                    conn,
                    is_sqlite=self.is_sqlite,
                    article_id=article_id,
                    images=images if isinstance(images, list) else [],
                    meta=article_meta if isinstance(article_meta, dict) else {},
                    videos=videos,
                    audios=audios,
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
        videos: Optional[List[Dict]] = None,
        audios: Optional[List[Dict]] = None,
        article_meta: Optional[Dict] = None,
    ) -> bool:
        """Insert/update un article. Dedup sur dedupe_key (guid ou lien normalise)."""
        from utils import article_dedupe_key, normalize_identifier, normalize_url
        from repositories.normalized_read import load_article_images, load_article_meta_norm
        from repositories.normalized_sync import sync_article_after_upsert

        link_n = normalize_url(link)
        if not link_n:
            return False
        guid_n = normalize_identifier(guid)
        key = article_dedupe_key(link_n, guid_n)
        feed_n = normalize_url(feed_url) or (feed_url or "")[:1000]

        async with self.pool.acquire() as conn:
            existing = await conn.fetchrow(
                """
                SELECT id, enrich_status
                FROM articles
                WHERE site_id = $1 AND dedupe_key = $2
                """,
                site_id,
                key[:2100],
            )

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

            art = await conn.fetchrow(
                """
                SELECT id FROM articles
                WHERE site_id = $1 AND dedupe_key = $2
                """,
                site_id,
                key[:2100],
            )
            if not art:
                return True

            article_id = int(art["id"])
            images_final = images if isinstance(images, list) else []
            meta_final = article_meta if isinstance(article_meta, dict) else {}

            # Si deja enrichi : ne pas ecraser images/meta normalises
            if existing and existing.get("enrich_status") == "ok":
                if images is not None:
                    images_final = await load_article_images(conn, article_id)
                if article_meta is not None:
                    norm = await load_article_meta_norm(conn, article_id)
                    if norm:
                        meta_final = {
                            "canonical_url": norm.get("canonical_url"),
                            "date_published": norm.get("date_published"),
                            "schema_type": norm.get("schema_type"),
                            "reading_time_minutes": norm.get("reading_time_minutes"),
                            "primary_image": norm.get("primary_image_url"),
                            "domain": norm.get("domain"),
                        }
                        extra = self._parse_json_field(norm.get("extra"))
                        if isinstance(extra, dict):
                            meta_final.update(extra)
                    meta_final = self._merge_article_meta_dict(meta_final, article_meta)
            elif existing and (images is not None or article_meta is not None):
                if images is not None:
                    images_final = self._merge_image_lists(
                        await load_article_images(conn, article_id), images
                    )
                if article_meta is not None:
                    # merge keywords/meta depuis tables via hydrate light
                    from repositories.normalized_read import load_article_keywords

                    kws = await load_article_keywords(conn, article_id)
                    base_meta = {"keywords": [k["keyword"] for k in kws]} if kws else {}
                    meta_final = self._merge_article_meta_dict(base_meta, article_meta)

            await sync_article_after_upsert(
                conn,
                is_sqlite=self.is_sqlite,
                site_id=site_id,
                article_id=article_id,
                feed_url=feed_n,
                images=images_final,
                meta=meta_final,
                videos=videos,
                audios=audios,
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
                    videos=getattr(art, "videos", None) or None,
                    audios=getattr(art, "audios", None) or None,
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