"""The two HTML pages and the look-and-feel contract: each opts into the shared v2 theme
(dark/light, sidebar) and keeps its colours on theme tokens so dark mode works."""
import re
from pathlib import Path

import pytest

from app import config

ROOT = Path(__file__).resolve().parent.parent
PAGES = ["/", "/settings.html"]


@pytest.mark.parametrize("path", PAGES)
def test_the_page_renders_with_the_shared_assets_url(client, path):
    resp = client.get(path)
    assert resp.status_code == 200
    html = resp.text
    assert f'{config.SHARED_ASSETS_BASE}/theme.css' in html
    assert f'{config.SHARED_ASSETS_BASE}/theme.js' in html
    assert "{{" not in html  # no unrendered template variables


@pytest.mark.parametrize("path", PAGES)
def test_the_page_opts_into_the_v2_look(client, path):
    html = client.get(path).text
    assert '<html lang="en" data-ui="v2">' in html
    # theme-init must run after theme.css (it reads --bg) and before the page paints.
    assert html.index("theme.css") < html.index("theme-init.js") < html.index("</head>")


@pytest.mark.parametrize("path", PAGES)
def test_every_script_the_page_names_exists(client, path):
    html = client.get(path).text
    for src in re.findall(r'<script src="([^"]+)"', html):
        if src.startswith("http"):
            continue
        assert client.get("/" + src).status_code == 200, src


def test_the_stylesheet_and_manifest_are_served(client):
    assert client.get("/style.css").status_code == 200
    assert client.get("/manifest.json").json()["name"]


def test_the_app_stylesheet_has_no_hard_coded_colours():
    css = (ROOT / "static" / "style.css").read_text()
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    assert re.findall(r"#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(", css) == []


def test_the_phone_bar_colour_is_not_fixed_in_the_templates():
    """theme-init.js / theme.js set <meta name=theme-color> from the page background for the
    current theme; a fixed one in a template would stay light in dark mode."""
    for name in ("index.html", "settings.html"):
        html = (ROOT / "templates" / name).read_text()
        assert 'name="theme-color"' not in html
