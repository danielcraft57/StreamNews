"""Tests extraction RSS (media, keywords)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.rss_entry import (
    entry_article_meta,
    entry_audios,
    entry_images,
    entry_keywords,
    entry_summary,
    entry_videos,
)


def test_entry_images_media_and_enclosure():
    entry = {
        "link": "https://news.example.com/a/1",
        "media_content": [{"url": "https://cdn.example.com/a.jpg", "medium": "image"}],
        "media_thumbnail": [{"url": "https://cdn.example.com/thumb.jpg"}],
        "enclosures": [{"href": "https://cdn.example.com/e.png", "type": "image/png"}],
        "summary": '<p>Hi</p><img src="https://cdn.example.com/inline.jpg" alt="x">',
    }
    urls = [img["url"] for img in entry_images(entry)]
    assert "https://cdn.example.com/a.jpg" in urls
    assert "https://cdn.example.com/inline.jpg" in urls


def test_entry_videos_and_audios():
    entry = {
        "link": "https://news.example.com/a/1",
        "media_content": [
            {"url": "https://cdn.example.com/v.mp4", "medium": "video", "type": "video/mp4"},
            {"url": "https://cdn.example.com/a.mp3", "medium": "audio"},
        ],
        "enclosures": [{"href": "https://cdn.example.com/pod.mp3", "type": "audio/mpeg"}],
    }
    vids = entry_videos(entry)
    auds = entry_audios(entry)
    assert any(v["url"].endswith("v.mp4") for v in vids)
    assert any(a["url"].endswith("pod.mp3") for a in auds)


def test_entry_keywords_from_tags():
    class Tag:
        def __init__(self, term):
            self.term = term

    entry = {"tags": [Tag("Tech"), Tag("RSS")], "category": "News"}
    assert "Tech" in entry_keywords(entry)
    assert "News" in entry_keywords(entry)


def test_entry_summary_strips_html():
    entry = {"summary": "<p>Hello <b>world</b></p>"}
    assert entry_summary(entry) == "Hello world"


def test_entry_article_meta_has_rss_source():
    meta = entry_article_meta({"tags": []})
    assert meta["sources"] == ["rss"]
