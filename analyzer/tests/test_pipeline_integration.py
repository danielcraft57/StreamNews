"""Integration Postgres : pages, feeds site, articles, enrichissement."""
import json
from datetime import datetime

import pytest

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_pages_stored_per_site(db, site_id):
    feeds = [{"url": "https://example.com/rss", "title": "RSS"}]
    await db.add_page_analysis(
        site_id, "https://example.com/", "Accueil", feeds
    )
    await db.add_page_analysis(
        site_id, "https://example.com/blog", "Blog", []
    )

    pages = await db.get_site_pages(site_id)
    assert len(pages) == 2
    titles = {p["title"] for p in pages}
    assert "Accueil" in titles
    assert "Blog" in titles
    home = next(p for p in pages if p["title"] == "Accueil")
    assert home["rss_feeds"][0]["url"] == "https://example.com/rss"


@pytest.mark.asyncio
async def test_site_feeds_merge_on_reanalysis(db, site_id):
    await db.update_site_status(
        site_id,
        "completed",
        [{"url": "https://example.com/rss", "title": "RSS"}],
        3,
        merge_feeds=True,
    )
    await db.update_site_status(
        site_id,
        "completed",
        [{"url": "https://example.com/atom", "title": "Atom"}],
        7,
        merge_feeds=True,
    )

    site = await db.get_site(site_id)
    urls = {f["url"] for f in site["rss_feeds"]}
    assert "https://example.com/rss" in urls
    assert "https://example.com/atom" in urls
    assert site["total_pages_analyzed"] == 7


@pytest.mark.asyncio
async def test_upsert_article_dedupes_http_https(db, site_id):
    await db.upsert_article(
        site_id=site_id,
        feed_url="https://example.com/rss",
        title="Titre A",
        link="http://example.com/article-1",
        summary="Resume",
        author="Bob",
    )
    await db.upsert_article(
        site_id=site_id,
        feed_url="https://example.com/rss",
        title="Titre B mis a jour",
        link="https://www.example.com/article-1/",
        summary="Nouveau resume",
    )

    articles = await db.get_site_articles(site_id)
    assert len(articles) == 1
    assert articles[0]["title"] == "Titre B mis a jour"
    assert articles[0]["summary"] == "Nouveau resume"


@pytest.mark.asyncio
async def test_upsert_article_dedupes_by_guid(db, site_id):
    await db.upsert_article(
        site_id=site_id,
        feed_url="https://example.com/rss",
        title="Via guid",
        link="https://example.com/p/99",
        guid="unique-guid-42",
    )
    await db.upsert_article(
        site_id=site_id,
        feed_url="https://example.com/rss",
        title="Meme guid autre url",
        link="https://example.com/autre-lien",
        guid="unique-guid-42",
    )

    articles = await db.get_site_articles(site_id)
    assert len(articles) == 1


@pytest.mark.asyncio
async def test_article_enrichment_persisted(db, site_id):
    await db.upsert_article(
        site_id=site_id,
        feed_url="https://example.com/rss",
        title="Article enrichi",
        link="https://example.com/enriched",
    )
    articles = await db.get_site_articles(site_id)
    article_id = articles[0]["id"]

    await db.update_article_enrichment(
        article_id,
        content_html="<p>Corps</p>",
        content_text="Corps",
        images=[{"url": "https://example.com/img.jpg", "alt": "", "source": "meta"}],
        article_meta={"author": "Alice", "sources": ["json-ld"]},
        enrich_status="ok",
        title="Titre enrichi",
    )

    full = await db.get_article(article_id)
    assert full["enrich_status"] == "ok"
    assert full["content_html"] == "<p>Corps</p>"
    assert full["content_text"] == "Corps"
    assert full["title"] == "Titre enrichi"
    assert full["images"][0]["url"] == "https://example.com/img.jpg"
    assert full["enriched_at"] is not None

    # Liste legere : pas de content_html
    listed = await db.get_site_articles(site_id)
    assert "content_html" not in listed[0]


@pytest.mark.asyncio
async def test_list_articles_needing_enrichment(db, site_id):
    await db.upsert_article(
        site_id, "https://example.com/rss", "A", "https://example.com/a"
    )
    await db.upsert_article(
        site_id, "https://example.com/rss", "B", "https://example.com/b"
    )
    articles = await db.get_site_articles(site_id)
    await db.update_article_enrichment(
        articles[0]["id"], enrich_status="ok", content_text="ok"
    )

    pending = await db.list_articles_needing_enrichment(site_id, limit=10)
    links = {p["link"] for p in pending}
    assert "https://example.com/b" in links
    assert "https://example.com/a" not in links


@pytest.mark.asyncio
async def test_delete_site_cascades_pages_and_articles(db, site_id):
    await db.add_page_analysis(site_id, "https://example.com/p", "P", [])
    await db.upsert_article(
        site_id, "https://example.com/rss", "X", "https://example.com/x"
    )

    result = await db.delete_site(site_id)
    assert result["deleted"]["pages"] == 1
    assert result["deleted"]["articles"] == 1
    assert await db.get_site(site_id) is None


@pytest.mark.asyncio
async def test_ingest_rss_articles_from_mocked_feed(db, site_id, monkeypatch):
    """ingest_rss_articles avec feedparser mocke (pas de reseau)."""
    import feedparser

    entry = type("Entry", (), {})()
    entry.title = "Flux mock"
    entry.link = "https://example.com/from-feed"
    entry.summary = "Resume flux"
    entry.author = "Editeur"
    entry.id = "feed-entry-1"
    entry.published_parsed = (2026, 7, 20, 8, 0, 0, 0, 0, 0)
    entry.updated_parsed = None
    entry.get = lambda k, d=None: {
        "link": entry.link,
        "id": entry.id,
        "summary": entry.summary,
        "description": None,
        "title": entry.title,
        "author": entry.author,
        "published_parsed": entry.published_parsed,
        "updated_parsed": None,
    }.get(k, d)

    parsed = type("Parsed", (), {"entries": [entry]})()
    monkeypatch.setattr(feedparser, "parse", lambda url: parsed)

    feeds = [{"url": "https://example.com/rss", "title": "RSS"}]
    count = await db.ingest_rss_articles(site_id, feeds)
    assert count == 1

    articles = await db.get_site_articles(site_id)
    assert len(articles) == 1
    assert articles[0]["title"] == "Flux mock"
    assert articles[0]["link"] == "https://example.com/from-feed"
