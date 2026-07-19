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
    assert "https://example.com/photo.jpg" in urls
    assert "https://example.com/hero.jpg" in urls


def test_extract_has_content_text_or_html():
    result = extract_from_html(SAMPLE_HTML, "https://example.com/news/1")
    assert result["content_text"] or result["content_html"]
    assert "<script" not in (result["content_html"] or "").lower()


def test_extract_empty_html():
    result = extract_from_html("", "https://example.com/x")
    assert result["content_html"] == ""
    assert result["images"] == []
