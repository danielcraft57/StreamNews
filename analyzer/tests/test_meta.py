from utils.meta import extract_site_meta


HOME = """
<html><head>
<title>Ma Boutique</title>
<meta name="description" content="Jeux et consoles">
<meta property="og:title" content="Boutique OG">
<meta property="og:image" content="/img/og.png">
<meta property="og:site_name" content="Shop">
<link rel="icon" href="/favicon.ico" sizes="32x32">
</head><body></body></html>
"""


def test_extract_site_meta_basic():
    meta = extract_site_meta("https://example.com/", HOME)
    assert meta["title"] == "Boutique OG"
    assert meta["description"] == "Jeux et consoles"
    assert meta["favicon_url"] == "https://example.com/favicon.ico"
    assert meta["og_image"] == "https://example.com/img/og.png"
    assert meta["og_site_name"] == "Shop"
