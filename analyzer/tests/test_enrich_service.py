"""Tests extraction structured data (JSON-LD / OG) sans fetch reseau."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.enrich_service import extract_from_html


SAMPLE_HTML = """<!DOCTYPE html>
<html>
<head>
  <title>Fallback title</title>
  <meta property="og:title" content="OG Title News">
  <meta property="og:description" content="Une description OG">
  <meta property="og:image" content="https://example.com/hero.jpg">
  <script type="application/ld+json">
  {
    "@context": "https://schema.org",
    "@type": "NewsArticle",
    "headline": "Titre JSON-LD Article",
    "description": "Resume schema.org",
    "datePublished": "2026-07-19T10:00:00Z",
    "author": {"@type": "Person", "name": "Alice Dupont"},
    "image": ["https://example.com/photo.jpg"],
    "articleBody": "Corps de l'article en schema.org. Deuxieme phrase."
  }
  </script>
</head>
<body>
  <article>
    <h1>Titre HTML</h1>
    <p>Paragraphe principal de l'article pour trafilatura.</p>
    <img src="/inline.png" alt="inline">
  </article>
</body>
</html>
"""


def test_extract_prefers_jsonld_title_and_author():
    result = extract_from_html(SAMPLE_HTML, "https://example.com/news/1")
    assert result["title"] == "Titre JSON-LD Article"
    assert result["author"] == "Alice Dupont"
    assert result["article_meta"].get("schema_type") == "newsarticle"
    assert "json-ld" in (result["article_meta"].get("sources") or [])


def test_extract_collects_images_from_meta():
    result = extract_from_html(SAMPLE_HTML, "https://example.com/news/1")
    urls = [img["url"] for img in result["images"]]
    assert "https://example.com/hero.jpg" in urls
    assert result["images"][0].get("primary") is True
    assert result["article_meta"].get("primary_image") == "https://example.com/hero.jpg"


def test_extract_has_content_text_or_html():
    result = extract_from_html(SAMPLE_HTML, "https://example.com/news/1")
    assert result["content_text"] or result["content_html"]
    assert "<script" not in (result["content_html"] or "").lower()


def test_extract_empty_html():
    result = extract_from_html("", "https://example.com/x")
    assert result["content_html"] == ""
    assert result["images"] == []


def test_extract_rdfa_and_page_meta():
    html = """<!DOCTYPE html><html><head>
    <link rel="canonical" href="https://example.com/news/1">
    <link rel="icon" href="/favicon.ico">
    <meta name="keywords" content="foo, bar">
    <meta property="og:title" content="RDFa OG Title">
    </head><body>
    <div typeof="schema:NewsArticle">
      <span property="schema:headline">RDFa Headline</span>
    </div>
    <p>Contenu article avec assez de mots pour une lecture.</p>
    </body></html>"""
    result = extract_from_html(html, "https://example.com/news/1")
    meta = result["article_meta"]
    assert meta.get("canonical_url") == "https://example.com/news/1"
    assert "foo" in (meta.get("keywords") or [])
    assert "rdfa" in (meta.get("sources") or []) or "page-meta" in (meta.get("sources") or [])
    assert meta.get("favicon_url", "").endswith("/favicon.ico")


def test_extract_dublin_core():
    html = """<!DOCTYPE html><html><head>
    <meta name="DC.title" content="DC Title">
    <meta name="DC.creator" content="Bob">
    <meta name="DC.subject" content="economie">
    </head><body><p>Texte.</p></body></html>"""
    result = extract_from_html(html, "https://example.com/dc")
    meta = result["article_meta"]
    assert meta.get("title") == "DC Title"
    assert meta.get("author") == "Bob"
    assert "dublin-core" in (meta.get("sources") or [])


def test_extract_strips_links_from_body():
    html = """<!DOCTYPE html><html><body><article>
    <p>Debut article avec <a href="https://spam.example/track">lien promo</a> au milieu.</p>
    <p>Suite https://example.com/raw-url dans le texte.</p>
    </article></body></html>"""
    result = extract_from_html(html, "https://example.com/news/links")
    text = result.get("content_text") or ""
    html_out = result.get("content_html") or ""
    assert "lien promo" in text or "lien promo" in html_out
    assert "https://spam.example" not in text
    assert "https://example.com/raw-url" not in text
    assert "<a" not in html_out.lower()
