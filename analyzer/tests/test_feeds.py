from utils.feeds import collapse_equivalent_feeds, overlap_ratio


def test_overlap_ratio_identical():
    a = {"a", "b", "c"}
    assert overlap_ratio(a, set(a)) == 1.0


def test_collapse_rss_and_atom_same_content():
    fps = {
        "https://example.com/feed": {"g1", "g2", "g3", "g4"},
        "https://example.com/feed/atom": {"g1", "g2", "g3", "g4"},
        "https://example.com/comments/feed": {"c1", "c2"},
    }
    feeds = [
        {
            "url": "https://example.com/feed",
            "type": "application/rss+xml",
            "title": "RSS Feed",
        },
        {
            "url": "https://example.com/feed/atom",
            "type": "application/atom+xml",
            "title": "Atom Feed",
        },
        {
            "url": "https://example.com/comments/feed",
            "type": "application/rss+xml",
            "title": "Comments",
        },
    ]
    kept = collapse_equivalent_feeds(feeds, fingerprints=fps)
    urls = [f["url"] for f in kept]
    assert "https://example.com/feed" in urls
    assert "https://example.com/feed/atom" not in urls
    assert "https://example.com/comments/feed" in urls
    assert len(kept) == 2


def test_collapse_prefers_rss_over_atom():
    fps = {
        "https://example.com/feed/atom": {"x"},
        "https://example.com/feed": {"x"},
    }
    feeds = [
        {"url": "https://example.com/feed/atom", "type": "application/atom+xml", "title": "Atom"},
        {"url": "https://example.com/feed", "type": "application/rss+xml", "title": "RSS"},
    ]
    kept = collapse_equivalent_feeds(feeds, fingerprints=fps)
    assert len(kept) == 1
    assert kept[0]["url"] == "https://example.com/feed"
