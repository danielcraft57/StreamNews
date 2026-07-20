"""Tests nettoyage texte (liens, URLs)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from text_analysis.clean import (
    prepare_text_for_analysis,
    strip_links_from_html,
    strip_urls_from_text,
)


def test_strip_urls_from_text():
    text = "Lire la suite sur https://example.com/foo et www.test.org/bar fin."
    assert "https://" not in strip_urls_from_text(text)
    assert "www." not in strip_urls_from_text(text)
    assert "Lire la suite" in strip_urls_from_text(text)


def test_strip_links_from_html_keeps_anchor_text():
    html = '<p>Intro <a href="https://x.com">lien utile</a> fin.</p>'
    out = strip_links_from_html(html)
    assert "<a" not in out.lower()
    assert "lien utile" in out


def test_prepare_text_for_analysis_from_html():
    html = '<p>Paragraphe <a href="https://x.com">sans lien</a> ici.</p>'
    text = prepare_text_for_analysis(None, html)
    assert "sans lien" in text
    assert "https://" not in text
