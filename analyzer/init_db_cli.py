"""CLI init DB avec logs etapes (scripts/init-db.*)."""
from __future__ import annotations

print("[init-db] script Python demarre", flush=True)

import argparse
import asyncio
import os
import time


def log(msg: str) -> None:
    print(f"[init-db] {msg}", flush=True)


def _mask_url(url: str) -> str:
    if "@" not in url or "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    if "@" not in rest:
        return url
    creds, host = rest.rsplit("@", 1)
    user = creds.split(":", 1)[0]
    return f"{scheme}://{user}:***@{host}"


async def run(reset: bool) -> None:
    t0 = time.perf_counter()

    log("chargement module database...")
    from database import Database

    db = Database()
    log(f"backend={db.backend} url={_mask_url(db.database_url)} (+{time.perf_counter() - t0:.1f}s)")

    try:
        do_reset = reset or os.getenv("STREAMNEWS_RESET_DB", "").strip() in ("1", "true", "yes")
        if do_reset:
            log("reset demande: alembic downgrade base + upgrade head")

        t_schema = time.perf_counter()
        log(f"migrations Alembic ({db.backend})...")
        from migrate import run_migrations

        run_migrations(db.database_url, reset=do_reset)
        log(f"migrations OK (+{time.perf_counter() - t_schema:.1f}s)")

        t_pool = time.perf_counter()
        log("connexion pool...")
        from db_backend import create_pool

        db.pool = await create_pool(db.database_url)
        db.backend = getattr(db.pool, "backend", db.backend)
        log(f"pool OK ({db.backend}) (+{time.perf_counter() - t_pool:.1f}s)")

        if not getattr(db, "_dedupe_ensured", False):
            t_dedupe = time.perf_counter()
            log("dedupe articles...")
            deleted = await db.ensure_article_dedupe()
            log(f"dedupe articles OK ({deleted} supprimes) (+{time.perf_counter() - t_dedupe:.1f}s)")

            t_domain = time.perf_counter()
            log("dedupe domaines sites...")
            dup_sites = await db.ensure_site_domain_unique()
            log(f"dedupe domaines OK ({dup_sites} fusionnes) (+{time.perf_counter() - t_domain:.1f}s)")

            db._dedupe_ensured = True
    finally:
        await db.close()

    log(f"termine (+{time.perf_counter() - t0:.1f}s total)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialise le schema StreamNews")
    parser.add_argument("--reset", action="store_true", help="DROP + recreate tables")
    args = parser.parse_args()
    asyncio.run(run(reset=args.reset))


if __name__ == "__main__":
    main()
