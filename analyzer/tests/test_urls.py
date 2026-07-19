from utils.urls import article_dedupe_key, normalize_identifier, normalize_url


def test_normalize_url_http_https_and_slash():
    assert normalize_url("http://Example.com/feed/") == "https://example.com/feed"
    assert normalize_url("https://www.example.com/a/") == "https://example.com/a"


def test_normalize_url_strips_utm():
    assert (
        normalize_url("https://example.com/a?utm_source=x&id=1")
        == "https://example.com/a?id=1"
    )


def test_article_dedupe_key_prefers_guid():
    k1 = article_dedupe_key(
        "https://example.com/post/",
        "http://example.com/?p=12",
    )
    k2 = article_dedupe_key(
        "http://example.com/post",
        "https://example.com/?p=12",
    )
    assert k1 == k2
    assert k1.startswith("g:")


def test_normalize_identifier_url():
    assert normalize_identifier("http://x.com/?p=1") == "https://x.com/?p=1"
