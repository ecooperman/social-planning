import pytest
import requests

from app.scraping import og_tags
from app.scraping.base import ScraperError
from app.scraping.registry import find_strategy


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.instagram.com/p/abc/", "instagram"),
        ("https://instagram.com/reel/x/", "instagram"),
        ("https://m.facebook.com/story", "facebook"),
        ("https://www.facebook.com/x/posts/1", "facebook"),
        ("https://fb.watch/abc", "facebook"),
    ],
)
def test_the_right_strategy_is_picked(url, expected):
    assert find_strategy(url).name == expected


@pytest.mark.parametrize(
    "url", ["https://example.com/", "https://notinstagram.com/p/x", "https://instagram.com.evil.example/p/x", "not a url"]
)
def test_lookalike_hosts_get_no_strategy(url):
    assert find_strategy(url) is None


class _Response:
    def __init__(self, text="", ok=True):
        self.text, self._ok = text, ok

    def raise_for_status(self):
        if not self._ok:
            raise requests.HTTPError("403")


def _page(*metas):
    return "<html><head>" + "".join(f'<meta property="og:{k}" content="{v}">' for k, v in metas) + "</head></html>"


def test_open_graph_tags_are_read_and_trimmed(monkeypatch):
    html = _page(("title", "  A cafe "), ("description", "Great coffee"), ("image", "https://img.example.com/a.jpg"))
    seen = {}

    def get(url, headers=None, timeout=None):
        seen.update(url=url, headers=headers)
        return _Response(html)

    monkeypatch.setattr(requests, "get", get)
    content = og_tags.fetch_og_tags("https://www.instagram.com/p/abc/")
    assert (content.title, content.description, content.image_url) == ("A cafe", "Great coffee", "https://img.example.com/a.jpg")
    assert "facebookexternalhit" in seen["headers"]["User-Agent"]  # the crawler identity that gets the real markup


def test_a_page_with_only_some_tags_still_works(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: _Response(_page(("title", "Only a title"))))
    content = og_tags.fetch_og_tags("https://www.facebook.com/x")
    assert content.title == "Only a title"
    assert content.description is None and content.image_url is None


def test_a_page_with_no_open_graph_data_is_an_error(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: _Response("<html><head></head></html>"))
    with pytest.raises(ScraperError, match="No Open Graph"):
        og_tags.fetch_og_tags("https://www.instagram.com/p/x/")


def test_empty_tag_values_count_as_missing(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: _Response(_page(("title", "   "))))
    with pytest.raises(ScraperError):
        og_tags.fetch_og_tags("https://www.instagram.com/p/x/")


def test_a_failed_request_becomes_a_scraper_error(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: _Response(ok=False))
    with pytest.raises(ScraperError, match="failed"):
        og_tags.fetch_og_tags("https://www.instagram.com/p/x/")

    def down(*a, **k):
        raise requests.ConnectionError("no route")

    monkeypatch.setattr(requests, "get", down)
    with pytest.raises(ScraperError):
        og_tags.fetch_og_tags("https://www.instagram.com/p/x/")
