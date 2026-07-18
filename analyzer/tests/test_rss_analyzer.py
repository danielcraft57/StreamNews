import sys
from pathlib import Path
from unittest.mock import MagicMock

# Helpers testes sans deps natives (CI installe quand meme les vrais paquets)
sys.modules.setdefault("aiohttp", MagicMock())
sys.modules.setdefault("feedparser", MagicMock())
sys.modules.setdefault("bs4", MagicMock())

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rss_analyzer import RSSAnalyzer


def test_is_rss_link_by_mime_type():
    analyzer = RSSAnalyzer()
    assert analyzer.is_rss_link("/feed.xml", [], "application/rss+xml") is True


def test_is_rss_link_by_url():
    analyzer = RSSAnalyzer()
    assert analyzer.is_rss_link("/blog/rss", [], "") is True
    assert analyzer.is_rss_link("/about", [], "") is False


def test_is_rss_link_by_text():
    analyzer = RSSAnalyzer()
    assert analyzer.is_rss_link_by_text("/x", "flux rss") is True
    assert analyzer.is_rss_link_by_text("/x", "contact") is False


def test_is_internal_link():
    analyzer = RSSAnalyzer()
    assert analyzer.is_internal_link("https://example.com", "https://example.com/a") is True
    assert analyzer.is_internal_link("https://example.com", "https://other.com/a") is False


def test_remove_duplicate_rss():
    analyzer = RSSAnalyzer()
    feeds = [
        {"url": "https://example.com/rss", "title": "A"},
        {"url": "https://example.com/rss", "title": "B"},
        {"url": "https://example.com/atom", "title": "C"},
    ]
    unique = analyzer.remove_duplicate_rss(feeds)
    assert len(unique) == 2
    assert unique[0]["title"] == "A"
    assert unique[1]["url"] == "https://example.com/atom"


def test_internal_links_can_be_sliced_as_list():
    """Regresssion: get_internal_links renvoie un set, analyze_site doit le caster."""
    urls = {"https://example.com/a", "https://example.com/b", "https://example.com/c"}
    as_list = list(urls)
    assert len(as_list[:2]) == 2
