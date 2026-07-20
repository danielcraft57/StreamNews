"""Integration Postgres : domaine unique + fusion feeds."""
import pytest

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_upsert_same_domain_returns_same_site_id(db):
    first = await db.upsert_site_for_analysis("https://www.bfmtv.com/", "pending")
    second = await db.upsert_site_for_analysis(
        "https://bfmtv.com/autre-chemin", "pending"
    )

    assert first["site_id"] == second["site_id"]
    assert first["reused"] is False
    assert second["reused"] is True
    assert second["domain"] == "bfmtv.com"

    sites = await db.get_all_sites()
    assert len(sites) == 1


@pytest.mark.asyncio
async def test_reanalysis_merges_rss_feeds(db, site_id):
    await db.update_site_status(
        site_id,
        "completed",
        [{"url": "https://example.com/rss", "title": "RSS 1"}],
        5,
        merge_feeds=True,
    )
    await db.update_site_status(
        site_id,
        "completed",
        [{"url": "https://example.com/atom", "title": "Atom"}],
        10,
        merge_feeds=True,
    )

    site = await db.get_site(site_id)
    urls = {f["url"] for f in site["rss_feeds"]}
    assert "https://example.com/rss" in urls
    assert "https://example.com/atom" in urls
    assert site["total_pages_analyzed"] == 10


@pytest.mark.asyncio
async def test_ensure_site_domain_unique_merges_existing_duplicates(db):
    """Simule 2 BFM deja en base avant contrainte UNIQUE."""
    async with db.pool.acquire() as conn:
        if db.is_sqlite:
            await conn.execute("DROP INDEX IF EXISTS sites_domain_key")
            await conn.execute(
                """
                INSERT INTO sites (url, status, domain)
                VALUES ($1, 'completed', 'bfmtv.com'),
                       ($2, 'completed', 'bfmtv.com')
                """,
                "https://www.bfmtv.com/",
                "https://bfmtv.com/actu",
            )
        else:
            await conn.execute(
                "ALTER TABLE sites DROP CONSTRAINT IF EXISTS sites_domain_key"
            )
            await conn.execute(
                """
                INSERT INTO sites (url, status, domain)
                VALUES
                    ($1, 'completed', 'bfmtv.com'),
                    ($2, 'completed', 'bfmtv.com')
                """,
                "https://www.bfmtv.com/",
                "https://bfmtv.com/actu",
            )
        rows = await conn.fetch(
            "SELECT id FROM sites WHERE domain = 'bfmtv.com' ORDER BY id"
        )
        assert len(rows) == 2
        await conn.execute(
            """
            INSERT INTO rss_feeds (site_id, url, title, feed_type)
            VALUES ($1, $2, 'A', 'rss'), ($3, $4, 'B', 'rss')
            """,
            rows[0]["id"],
            "https://bfmtv.com/feed-a",
            rows[1]["id"],
            "https://bfmtv.com/feed-b",
        )

    deleted = await db.ensure_site_domain_unique()
    assert deleted == 1

    sites = await db.get_all_sites()
    assert len(sites) == 1
    urls = {f["url"] for f in sites[0]["rss_feeds"]}
    assert "https://bfmtv.com/feed-a" in urls
    assert "https://bfmtv.com/feed-b" in urls
