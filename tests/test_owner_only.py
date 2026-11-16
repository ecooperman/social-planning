"""The whole app is private to its administrators. It has no accounts of its own, so this is the only thing between
the internet and the data once Cloudflare Access is no longer in front of it. The sweep calls EVERY route with no
sign-in and with someone who is not an administrator; a route added later cannot slip past (the gate is middleware
around the whole app) and this fails if one ever does."""
import re
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from shared_python import auth, settings

from app import access, config
from app.main import app

ISSUER = "https://login.example.com"
CLIENT = "client-123"
FRONT = "https://dashboard.example.org"
TOKEN = "plans-service-secret"
PAGES = ["/", "/settings.html"]


@pytest.fixture(scope="module")
def key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture()
def production(monkeypatch, key):
    monkeypatch.setattr(settings, "ENV", "production")
    monkeypatch.setattr(config, "ADMIN_EMAILS", {"owner@example.com"})
    monkeypatch.setattr(settings, "OIDC_ISSUER", ISSUER)
    monkeypatch.setattr(settings, "OIDC_AUDIENCE", CLIENT)
    monkeypatch.setattr(settings, "OIDC_LOGIN_URL", FRONT + "/auth/login")
    monkeypatch.setattr(auth, "_oidc_signing_key", lambda _t: key.public_key())
    return TestClient(app, base_url="https://plans.example.org", follow_redirects=False)


def session(key, email):
    return jwt.encode(
        {"iss": ISSUER, "aud": CLIENT, "exp": int(time.time()) + 300, "email": email, "email_verified": True}, key, algorithm="RS256"
    )


def every_route():
    for shown, operations in app.openapi()["paths"].items():
        for method in operations:
            if method.upper() not in ("HEAD", "OPTIONS"):
                yield method.upper(), shown, re.sub(r"\{[^}]+\}", "1", shown)


def call(client, method, path):
    body = {"json": {}} if method in ("POST", "PUT", "PATCH") else {}
    return client.request(method, path, **body)


def test_nobody_signed_out_gets_anything_from_any_route(production):
    answered = []
    for method, shown, path in every_route():
        resp = call(production, method, path)
        if resp.status_code not in (401, 302):
            answered.append((method, shown, resp.status_code))
    for page in PAGES + ["/app.js", "/style.css", "/settings.js", "/nav.js", "/nope"]:
        if production.get(page).status_code != 302:
            answered.append(("GET", page))
    assert not answered, f"answered with no sign-in: {answered}"


def test_nobody_signed_in_as_a_stranger_gets_anything_either(production, key):
    production.cookies.set("oidc_session", session(key, "stranger@example.com"))
    answered = [
        (method, shown, call(production, method, path).status_code)
        for method, shown, path in every_route()
        if call(production, method, path).status_code != 403
    ]
    assert not answered, f"answered a signed-in stranger: {answered}"
    assert production.get("/").status_code == 403 and production.get("/app.js").status_code == 403


def test_the_administrator_gets_the_app(production, key):
    production.cookies.set("oidc_session", session(key, "owner@example.com"))
    for page in PAGES:
        assert production.get(page).status_code == 200
    assert production.get("/api/plans").status_code == 200


def test_a_signed_out_visitor_to_a_page_is_sent_to_sign_in_and_back(production):
    resp = production.get("/settings.html")
    assert resp.status_code == 302 and resp.headers["location"].startswith(FRONT + "/auth/login?next=")


def test_the_manifest_and_icons_stay_public_so_the_app_can_be_installed(production):
    assert production.get("/manifest.json").status_code == 200
    assert production.get("/icons/icon-192.png").status_code == 200
    assert production.get("/icons/../app.js").status_code in (302, 401, 404)


def test_without_an_administrator_configured_in_production_nobody_gets_in(production, key, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_EMAILS", set())
    production.cookies.set("oidc_session", session(key, "owner@example.com"))
    assert production.get("/api/plans").status_code == 503


def test_locally_the_dev_user_is_the_administrator(client):
    assert client.get("/").status_code == 200 and client.get("/api/plans").status_code == 200


# --- trip-planning's plan picker: three reads, with the service token, and nothing else -----------------------------


@pytest.fixture()
def with_token(production, monkeypatch):
    monkeypatch.setattr(config, "PLANS_SERVICE_TOKEN", TOKEN)
    return production


@pytest.mark.parametrize("path", ["/api/locations", "/api/plans", "/api/plans/1"])
def test_the_three_agreed_reads_work_with_the_token(with_token, path):
    assert with_token.get(path, headers={"X-Service-Token": TOKEN}).status_code in (200, 404)  # allowed through; 404 = no such plan


def test_every_other_route_refuses_the_token(with_token):
    leaked = []
    for method, shown, path in every_route():
        agreed = method == "GET" and re.fullmatch(r"/api/(locations|plans|plans/\d+)", path)
        if agreed:
            continue
        resp = call(with_token, method, path) if False else with_token.request(method, path, headers={"X-Service-Token": TOKEN}, **({"json": {}} if method in ("POST", "PUT", "PATCH") else {}))
        if resp.status_code not in (401, 302):
            leaked.append((method, shown, resp.status_code))
    assert not leaked, f"the service token opened: {leaked}"


@pytest.mark.parametrize("headers", [{}, {"X-Service-Token": "wrong"}, {"X-Service-Token": ""}])
def test_the_reads_are_refused_without_the_right_token(with_token, headers):
    assert with_token.get("/api/plans", headers=headers).status_code == 401


def test_the_token_does_nothing_when_none_is_configured(production):
    assert production.get("/api/plans", headers={"X-Service-Token": TOKEN}).status_code == 401
    assert production.get("/api/plans", headers={"X-Service-Token": ""}).status_code == 401


def test_the_token_cannot_be_used_to_write_or_to_reach_a_page(with_token):
    assert with_token.post("/api/plans", json={"name": "x"}, headers={"X-Service-Token": TOKEN}).status_code == 401
    assert with_token.get("/", headers={"X-Service-Token": TOKEN}).status_code == 302
    assert with_token.get("/api/plans/1/extra", headers={"X-Service-Token": TOKEN}).status_code in (401, 302)
    assert with_token.get("/api/plans/abc", headers={"X-Service-Token": TOKEN}).status_code == 401


# --- who is signed in, for the header's Log out -----------------------------------------------------------------------


def test_me_says_who_is_signed_in_and_where_log_out_goes(production, key):
    production.cookies.set("oidc_session", session(key, "Owner@Example.com"))
    assert production.get("/api/me").json() == {"email": "owner@example.com", "is_admin": True, "logout_url": FRONT + "/auth/logout"}


def test_me_is_refused_to_anyone_who_is_not_signed_in_or_not_an_administrator(production, key):
    assert production.get("/api/me").status_code == 401
    production.cookies.set("oidc_session", session(key, "stranger@example.com"))
    assert production.get("/api/me").status_code == 403


def test_locally_me_is_the_dev_user_with_no_front_door(client):
    me = client.get("/api/me").json()
    assert me["email"] == config.DEV_USER_EMAIL and me["logout_url"] is None


# --- cross-app request forgery -------------------------------------------------------------------------------------------


def test_every_route_that_changes_something_refuses_a_request_from_another_app_or_site(production, key):
    """The sign-in cookie covers every subdomain and subdomains are the same site, so a page on another app could make
    the owner's browser change things here. The browser marks such a request (Sec-Fetch-Site), and every route that
    changes anything must refuse it even with a valid administrator cookie (shared_python.csrf)."""
    production.cookies.set("oidc_session", session(key, "owner@example.com"))
    tried = 0
    for method, shown, path in every_route():
        if method not in ("POST", "PUT", "PATCH", "DELETE"):
            continue
        for site in ("same-site", "cross-site"):
            resp = production.request(method, path, json={}, headers={"Sec-Fetch-Site": site, "Origin": "https://lists.example.org"})
            assert resp.status_code == 403 and "didn't come from this app" in resp.text, (method, shown, site, resp.status_code)
            tried += 1
    assert tried > 4


def test_the_owner_can_still_make_changes_from_the_apps_own_pages(production, key):
    production.cookies.set("oidc_session", session(key, "owner@example.com"))
    for method, shown, path in every_route():
        if method == "POST" and "{" not in shown:
            resp = production.post(path, json={}, headers={"Sec-Fetch-Site": "same-origin", "Origin": str(production.base_url).rstrip("/")})
            assert "didn't come from this app" not in resp.text
            return
    pytest.fail("no plain POST route found")
