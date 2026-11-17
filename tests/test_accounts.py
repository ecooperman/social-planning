"""Several people can use this app, and each person's plans and places are completely private to them.

The tests that matter most are the two-person ones: one person makes data, then ANOTHER person with a valid account
tries every route of the app against it (reading, listing, changing, deleting, pointing their own data at it) and must
get nothing and change nothing. Alongside: who can get in at all (default-deny), that no sign-in trick makes one person
another, who may invite, and that what costs money or acts as the administrator stays the administrator's."""
import re
import sqlite3
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from shared_python import auth, owned, settings

from app import access, config, crud, models, notify
from app.main import app

ISSUER = "https://login.example.com"
CLIENT = "client-123"
FRONT = "https://dashboard.example.org"
ADMIN = "owner@example.com"
BOB_MARK = "SECRET-BOB-PLAN-XYZ"
BOB_PLACE = "Bobtown-Secret-Place"
TOKEN = "plans-service-secret"
OWNED_TABLES = (models.Country, models.Region, models.City, models.Location, models.Plan)


@pytest.fixture(scope="module")
def key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture()
def production(monkeypatch, key):
    monkeypatch.setattr(settings, "ENV", "production")
    monkeypatch.setattr(config, "ADMIN_EMAILS", {ADMIN})
    monkeypatch.setattr(settings, "OIDC_ISSUER", ISSUER)
    monkeypatch.setattr(settings, "OIDC_AUDIENCE", CLIENT)
    monkeypatch.setattr(settings, "OIDC_LOGIN_URL", FRONT + "/auth/login")
    monkeypatch.setattr(auth, "_oidc_signing_key", lambda _t: key.public_key())
    sent = []
    monkeypatch.setattr(notify, "tell_let_in", lambda to, inviter: sent.append((to, inviter)))
    return sent


def session(key, email, **kw):
    claims = {"iss": ISSUER, "aud": CLIENT, "exp": int(time.time()) + 300, "email": email, "email_verified": True}
    claims.update(kw)
    return jwt.encode(claims, key, algorithm="RS256")


@pytest.fixture()
def person(key, production):
    def make(email, **kw):
        c = TestClient(app, base_url="https://plans.example.org", follow_redirects=False)
        c.cookies.set("oidc_session", session(key, email, **kw))
        return c

    return make


@pytest.fixture()
def people(make_user):
    """Bob and Carol have accounts; Dana does not; Eve's access was removed."""
    return {"bob": make_user("bob@example.com"), "carol": make_user("carol@example.com"),
            "eve": make_user("eve@example.com", status=models.USER_REMOVED)}


def fill_bobs_data(bob):
    """Everything a person can own, with recognisable names."""
    loc = bob.post("/api/locations", json={"name": BOB_PLACE, "new_country": "Bobland", "new_region": "Bobshire", "new_city": "Bobtown"})
    assert loc.status_code == 200, loc.text
    plan = bob.post("/api/plans", json={"name": BOB_MARK, "location_id": loc.json()["id"], "description": "private", "url": "https://example.com/b"})
    assert plan.status_code == 200, plan.text
    return snapshot(bob)


def snapshot(who):
    return {name: who.get(f"/api/{name}").json() for name in ("countries", "regions", "cities", "locations", "plans")}


def every_route():
    for shown, operations in app.openapi()["paths"].items():
        for method in operations:
            if method.upper() not in ("HEAD", "OPTIONS"):
                yield method.upper(), shown


def fill(shown, ids):
    def sub(match):
        name = match.group(1)
        return str(ids.get(name, "x" if name == "place_id" else 1))

    return re.sub(r"\{([^}]+)\}", sub, shown)


BODIES = {"name": "HIJACKED", "description": "HIJACKED", "text": "HIJACKED", "status": "removed", "email": "hijack@example.com"}


# --- who gets in (default-deny) ---------------------------------------------------------------------------------------


def test_a_person_with_an_account_gets_in(person, people):
    assert person("bob@example.com").get("/api/me").json()["id"] == people["bob"]


def test_signed_in_is_not_enough_a_person_nobody_let_in_gets_nothing_from_any_route(person, people):
    dana = person("dana@example.com")
    leaked = []
    for method, shown in every_route():
        resp = dana.request(method, fill(shown, {}), json={} if method in ("POST", "PATCH", "PUT") else None)
        if resp.status_code != 403:
            leaked.append((method, shown, resp.status_code))
    assert not leaked, leaked
    page = dana.get("/")
    assert page.status_code == 403 and "have access yet" in page.text and "dana@example.com" in page.text
    assert f'href="{FRONT}/auth/logout"' in page.text


def test_a_person_whose_access_was_removed_gets_nothing_and_is_told_so(person, people):
    eve = person("eve@example.com")
    assert eve.get("/api/plans").status_code == 403 and eve.get("/api/me").status_code == 403
    assert "access was removed" in eve.get("/").text


def test_nobody_signed_out_gets_anything(person, people):
    signed_out = TestClient(app, base_url="https://plans.example.org", follow_redirects=False)
    answered = []
    for method, shown in every_route():
        resp = signed_out.request(method, fill(shown, {}), json={} if method in ("POST", "PATCH", "PUT") else None)
        if resp.status_code not in (401, 302):
            answered.append((method, shown, resp.status_code))
    for path in ("/", "/settings.html", "/users.html", "/app.js", "/style.css", "/nope"):
        if signed_out.get(path).status_code != 302:
            answered.append(("GET", path))
    assert not answered, answered


def test_the_first_administrator_to_sign_in_gets_an_account_and_a_stranger_posing_as_one_does_not(person, people):
    assert person(ADMIN).get("/api/me").json()["is_admin"] is True
    assert person("owner+x@example.com").get("/api/me").status_code == 403  # a plus alias is a different person
    assert person("Owner@Example.com").get("/api/me").json()["email"] == ADMIN  # case does not matter


# --- no sign-in trick makes one person another --------------------------------------------------------------------------------


def test_a_token_signed_by_anyone_else_is_refused(person, people, key):
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    forged = jwt.encode({"iss": ISSUER, "aud": CLIENT, "exp": int(time.time()) + 300, "email": "bob@example.com", "email_verified": True}, other, algorithm="RS256")
    c = TestClient(app, base_url="https://plans.example.org", follow_redirects=False)
    c.cookies.set("oidc_session", forged)
    assert c.get("/api/plans").status_code == 401


@pytest.mark.parametrize("kw", [{"aud": "another-app"}, {"email_verified": False}, {"exp": 1}, {"iss": "https://evil.example.com"}])
def test_a_token_for_the_wrong_app_issuer_unverified_or_expired_is_refused(person, people, kw):
    assert person("bob@example.com", **kw).get("/api/plans").status_code == 401


def test_a_claim_of_identity_in_a_header_or_cookie_is_never_trusted(person, people):
    c = TestClient(app, base_url="https://plans.example.org", follow_redirects=False)
    for headers in ({"Cf-Access-Authenticated-User-Email": "bob@example.com"}, {"X-Forwarded-User": "bob@example.com"}):
        assert c.get("/api/plans", headers=headers).status_code == 401
    assert c.get("/api/plans", cookies={"dev_user": "bob@example.com"}).status_code == 401


def test_a_body_or_query_naming_another_person_changes_nothing(person, people):
    bob, carol = person("bob@example.com"), person("carol@example.com")
    fill_bobs_data(bob)
    before = snapshot(bob)
    for extra in ({"owner_id": people["bob"]}, {"user_id": people["bob"]}, {"email": "bob@example.com"}):
        resp = carol.post("/api/plans", json={"name": "carols", **extra})
        assert resp.status_code in (200, 422)  # the extra fields are simply ignored
    mine = carol.get("/api/plans", params={"owner_id": people["bob"], "user_id": people["bob"]}).json()
    assert {p["name"] for p in mine} == {"carols"} and BOB_MARK not in str(mine)  # all hers, none Bob's
    assert snapshot(bob) == before  # and nothing was added to or taken from Bob


# --- whose data they see: the two-person tests ----------------------------------------------------------------------------------


def test_each_person_sees_only_their_own_plans_and_places(person, people):
    bob, carol = person("bob@example.com"), person("carol@example.com")
    fill_bobs_data(bob)
    carol.post("/api/plans", json={"name": "carols-plan"})
    assert [p["name"] for p in bob.get("/api/plans").json()] == [BOB_MARK]
    assert [p["name"] for p in carol.get("/api/plans").json()] == ["carols-plan"]
    assert carol.get("/api/locations").json() == [] and carol.get("/api/countries").json() == []


def test_another_person_can_neither_read_nor_change_nor_delete_anything_through_any_route(person, people):
    """Bob owns data; Carol, with a perfectly valid account, calls EVERY route of the app aimed at Bob's rows."""
    bob, carol = person("bob@example.com"), person("carol@example.com")
    before = fill_bobs_data(bob)
    ids = {
        "plan_id": before["plans"][0]["id"], "location_id": before["locations"][0]["id"], "country_id": before["countries"][0]["id"],
        "region_id": before["regions"][0]["id"], "city_id": before["cities"][0]["id"], "user_id": people["bob"],
    }
    tried, leaked = 0, []
    for method, shown in every_route():
        path = fill(shown, ids)
        kwargs = {}
        if method in ("POST", "PATCH", "PUT"):
            kwargs["json"] = {**BODIES, "location_id": ids["location_id"], "country_id": ids["country_id"], "plan_ids": [ids["plan_id"]]}
        resp = carol.request(method, path, params={"location_id": ids["location_id"], "country_id": ids["country_id"]}, **kwargs)
        tried += 1
        if BOB_MARK in resp.text or BOB_PLACE in resp.text or "Bobland" in resp.text or "Bobtown" in resp.text:
            leaked.append((method, shown, "data in the response"))
        if method in ("PATCH", "PUT", "DELETE") and resp.status_code < 300:
            leaked.append((method, shown, resp.status_code))
        if method == "GET" and "{" in shown and resp.status_code == 200:
            leaked.append((method, shown, "an id route answered"))
    assert tried > 15 and not leaked, leaked
    assert snapshot(bob) == before  # not a name, a link or a row changed
    assert snapshot(carol) == {k: [] for k in before}  # and nothing was created for Carol by those calls either


def test_pointing_ones_own_data_at_someone_elses_is_refused(person, people):
    bob, carol = person("bob@example.com"), person("carol@example.com")
    before = fill_bobs_data(bob)
    bobs_loc, bobs_country = before["locations"][0]["id"], before["countries"][0]["id"]
    assert carol.post("/api/plans", json={"name": "x", "location_id": bobs_loc}).status_code == 400
    assert carol.post("/api/locations", json={"name": "Mine", "country_id": bobs_country}).status_code == 400
    mine = carol.post("/api/plans", json={"name": "mine"}).json()["id"]
    assert carol.patch(f"/api/plans/{mine}", json={"location_id": bobs_loc}).status_code == 400
    assert snapshot(bob) == before


def test_two_people_may_each_have_a_country_and_a_location_with_the_same_name(person, people):
    bob, carol = person("bob@example.com"), person("carol@example.com")
    for who in (bob, carol):
        assert who.post("/api/locations", json={"name": "Salem, MA", "new_country": "United States"}).status_code == 200
    assert len(bob.get("/api/locations").json()) == 1 and len(carol.get("/api/locations").json()) == 1
    assert bob.get("/api/countries").json()[0]["id"] != carol.get("/api/countries").json()[0]["id"]


def test_the_administrator_is_just_another_owner_and_cannot_read_a_persons_plans_through_the_app(person, people):
    bob, admin = person("bob@example.com"), person(ADMIN)
    before = fill_bobs_data(bob)
    assert admin.get("/api/plans").json() == [] and BOB_MARK not in admin.get("/api/locations").text
    assert admin.get(f"/api/plans/{before['plans'][0]['id']}").status_code == 404
    assert admin.delete(f"/api/plans/{before['plans'][0]['id']}").status_code == 404
    assert snapshot(bob) == before


def test_removing_a_person_locks_them_out_at_once_and_keeps_their_data_private_until_deleted(person, people):
    bob, admin = person("bob@example.com"), person(ADMIN)
    before = fill_bobs_data(bob)
    assert admin.patch(f"/api/users/{people['bob']}", json={"status": "removed"}).status_code == 200
    assert bob.get("/api/plans").status_code == 403
    assert admin.get("/api/plans").json() == []  # still nobody else's
    admin.patch(f"/api/users/{people['bob']}", json={"status": "active"})
    assert snapshot(bob) == before  # restored: everything is still there


# --- what costs money or acts as the administrator stays the administrator's ------------------------------------------------


def test_only_an_administrator_can_use_the_google_lookup_the_instagram_import_and_send_to_trips(person, people):
    carol = person("carol@example.com")
    for method, path, body in [
        ("GET", "/api/locations/lookup?q=paris", None), ("GET", "/api/locations/lookup/abc", None),
        ("POST", "/api/instagram-import", {"posts": [{"permalink": "https://www.instagram.com/p/x/", "caption": "c"}]}),
        ("GET", "/api/trips-link/trips", None), ("GET", "/api/trips-link/links", None), ("POST", "/api/trips-link/send", {"plan_ids": [1]}),
    ]:
        resp = carol.request(method, path, json=body)
        assert resp.status_code == 403, (method, path, resp.status_code)
    assert carol.get("/api/locations/lookup/available").json() == {"available": False}
    me = carol.get("/api/me").json()
    assert me["is_admin"] is False and me["can_use"] == {"places": False, "instagram": False, "trips": False}


def test_the_administrator_is_offered_them(person, people, monkeypatch):
    monkeypatch.setattr("app.places.available", lambda: True)
    me = person(ADMIN).get("/api/me").json()
    assert me["is_admin"] is True and me["can_use"] == {"places": True, "instagram": True, "trips": True}


def test_a_link_typed_into_a_plan_never_brings_anything_back_from_the_servers_own_network(person, people):
    carol = person("carol@example.com")
    pid = carol.post("/api/plans", json={"name": "p", "url": "http://127.0.0.1:8080/api/balance"}).json()["id"]
    resp = carol.post(f"/api/plans/{pid}/scrape")
    assert resp.status_code == 200
    plan = carol.get(f"/api/plans/{pid}").json()
    assert plan["scrape_status"] != "success"
    assert plan["scraped_title"] is None and plan["scraped_description"] is None and plan["scraped_image_url"] is None


# --- who may invite: only administrators ---------------------------------------------------------------------------------------------


def test_only_an_administrator_may_list_add_change_or_delete_people(person, people):
    carol = person("carol@example.com")
    assert carol.get("/api/users").status_code == 403
    assert carol.post("/api/users", json={"email": "friend@example.com"}).status_code == 403
    assert carol.patch(f"/api/users/{people['bob']}", json={"status": "removed"}).status_code == 403
    assert carol.delete(f"/api/users/{people['bob']}/data").status_code == 403
    assert person("bob@example.com").get("/api/plans").status_code == 200  # untouched
    assert person("friend@example.com").get("/api/plans").status_code == 403  # and nobody was let in


def test_an_administrator_lets_someone_in_and_they_are_told_by_email(person, production, people):
    admin = person(ADMIN)
    resp = admin.post("/api/users", json={"email": "  Newbie@Example.COM "})
    assert resp.status_code == 200 and resp.json()["email"] == "newbie@example.com"
    assert production == [("newbie@example.com", ADMIN)]
    newbie = person("newbie@example.com")
    assert newbie.get("/api/plans").json() == []
    assert admin.post("/api/users", json={"email": "newbie@example.com"}).status_code == 200
    assert production == [("newbie@example.com", ADMIN)]  # not told again: nothing changed


def test_adding_a_removed_person_restores_them_and_tells_them(person, production, people):
    admin = person(ADMIN)
    assert person("eve@example.com").get("/api/plans").status_code == 403
    assert admin.post("/api/users", json={"email": "eve@example.com"}).status_code == 200
    assert person("eve@example.com").get("/api/plans").status_code == 200 and production == [("eve@example.com", ADMIN)]


@pytest.mark.parametrize("email", ["", "no-at-sign", "a@b", "x@y.", "@example.com", "legacy-owner@plans.invalid", "a b@example.com"])
def test_a_bad_address_is_refused(person, people, email):
    assert person(ADMIN).post("/api/users", json={"email": email or " "}).status_code in (400, 422)


def test_an_administrators_access_cannot_be_changed_or_removed_from_the_users_page(person, production, people, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_EMAILS", {ADMIN, "second@example.com"})
    admin = person(ADMIN)
    person("second@example.com").get("/api/me")
    users = {u["email"]: u for u in admin.get("/api/users").json()}
    assert users["second@example.com"]["is_admin"] is True
    assert admin.patch(f"/api/users/{users['second@example.com']['id']}", json={"status": "removed"}).status_code == 409
    me = admin.get("/api/me").json()["id"]
    assert admin.patch(f"/api/users/{me}", json={"status": "removed"}).status_code == 409


def test_deleting_a_removed_persons_data_deletes_exactly_theirs(person, people):
    bob, carol, admin = person("bob@example.com"), person("carol@example.com"), person(ADMIN)
    fill_bobs_data(bob)
    carols = fill_bobs_data(carol) if False else None
    carol.post("/api/plans", json={"name": "carols-plan"})
    assert admin.delete(f"/api/users/{people['bob']}/data").status_code == 409  # not removed yet
    admin.patch(f"/api/users/{people['bob']}", json={"status": "removed"})
    deleted = admin.delete(f"/api/users/{people['bob']}/data").json()["deleted"]
    assert deleted["plans"] == 1 and deleted["locations"] == 1 and deleted["countries"] == 1
    with owned.unscoped():
        from app.database import SessionLocal

        with SessionLocal() as s:
            assert s.query(models.Plan).filter(models.Plan.owner_id == people["bob"]).count() == 0
            assert [p.name for p in s.query(models.Plan).all()] == ["carols-plan"]
    assert carols is None and [p["name"] for p in carol.get("/api/plans").json()] == ["carols-plan"]


# --- the data from before accounts -------------------------------------------------------------------------------------------------


def test_the_first_administrator_takes_over_the_data_that_existed_before_accounts_and_nobody_else_does(person, people):
    with owned.unscoped():
        from app.database import SessionLocal

        with SessionLocal() as s:
            legacy = models.User(email=crud.LEGACY_OWNER_EMAIL)
            s.add(legacy)
            s.flush()
            s.add(models.Plan(name="from-before-accounts", owner_id=legacy.id))
            s.commit()
    assert [p["name"] for p in person("bob@example.com").get("/api/plans").json()] == []  # an ordinary person gets none of it
    assert [p["name"] for p in person(ADMIN).get("/api/plans").json()] == ["from-before-accounts"]
    assert person("carol@example.com").get("/api/plans").json() == []
    assert person(ADMIN).get("/api/users").json()  # and the placeholder is not listed as a person
    assert all(u["email"] != crud.LEGACY_OWNER_EMAIL for u in person(ADMIN).get("/api/users").json())


# --- trip-planning's plan picker ----------------------------------------------------------------------------------------------------------


@pytest.fixture()
def with_token(monkeypatch):
    monkeypatch.setattr(config, "PLANS_SERVICE_TOKEN", TOKEN)


def test_the_service_token_acts_as_the_administrator_and_sees_only_the_administrators_plans(person, people, with_token):
    bob, admin = person("bob@example.com"), person(ADMIN)
    fill_bobs_data(bob)
    admin.post("/api/plans", json={"name": "admins-plan"})
    machine = TestClient(app, base_url="https://plans.example.org", follow_redirects=False)
    got = machine.get("/api/plans", headers={"X-Service-Token": TOKEN})
    assert got.status_code == 200 and [p["name"] for p in got.json()] == ["admins-plan"] and BOB_MARK not in got.text


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/me"), ("GET", "/api/users"), ("POST", "/api/plans"), ("DELETE", "/api/plans/1"), ("GET", "/api/countries"),
    ("GET", "/api/trips-link/trips"), ("POST", "/api/instagram-import"), ("GET", "/"), ("GET", "/api/plans/1/extra"),
])
def test_the_service_token_opens_nothing_but_the_three_agreed_reads(person, people, with_token, method, path):
    machine = TestClient(app, base_url="https://plans.example.org", follow_redirects=False)
    resp = machine.request(method, path, headers={"X-Service-Token": TOKEN}, json={} if method == "POST" else None)
    assert resp.status_code in (401, 302)


def test_a_wrong_or_missing_token_or_none_configured_opens_nothing(person, people, monkeypatch):
    machine = TestClient(app, base_url="https://plans.example.org", follow_redirects=False)
    monkeypatch.setattr(config, "PLANS_SERVICE_TOKEN", TOKEN)
    for headers in ({}, {"X-Service-Token": "wrong"}, {"X-Service-Token": ""}):
        assert machine.get("/api/plans", headers=headers).status_code == 401
    monkeypatch.setattr(config, "PLANS_SERVICE_TOKEN", None)
    assert machine.get("/api/plans", headers={"X-Service-Token": TOKEN}).status_code == 401


# --- the rest of the gate ----------------------------------------------------------------------------------------------------------------------


def test_the_manifest_and_icons_are_public_and_nothing_else_is(person, people):
    signed_out = TestClient(app, base_url="https://plans.example.org", follow_redirects=False)
    assert signed_out.get("/manifest.json").status_code == 200 and signed_out.get("/icons/icon-192.png").status_code == 200
    for path in ("/app.js", "/settings.js", "/api/plans", "/icons/../app.js"):
        assert signed_out.get(path).status_code in (302, 401, 404)


def test_every_route_that_changes_something_refuses_a_request_from_another_app_or_site(person, people):
    bob = person("bob@example.com")
    tried = 0
    for method, shown in every_route():
        if method not in ("POST", "PUT", "PATCH", "DELETE"):
            continue
        for site in ("same-site", "cross-site"):
            resp = bob.request(method, fill(shown, {}), json={}, headers={"Sec-Fetch-Site": site, "Origin": "https://lists.example.org"})
            assert resp.status_code == 403 and "didn't come from this app" in resp.text, (method, shown, site)
            tried += 1
    assert tried > 10
    assert bob.get("/api/plans").json() == []


def test_me_says_who_is_signed_in_and_where_log_out_goes(person, people):
    me = person("bob@example.com").get("/api/me").json()
    assert me["email"] == "bob@example.com" and me["logout_url"] == FRONT + "/auth/logout" and me["is_admin"] is False


def test_locally_the_dev_user_is_an_administrator_with_an_account(client, client_as, make_user):
    assert client.get("/api/me").json()["is_admin"] is True
    make_user("bob@example.com")
    assert client_as("bob@example.com").get("/api/me").json()["is_admin"] is False
    assert client_as("nobody@example.com").get("/api/me").status_code == 403


def test_no_code_in_the_app_bypasses_the_owner_filter():
    owned.assert_no_raw_sql(["app"])


def test_every_table_of_a_persons_data_has_an_owner_and_the_filter_covers_it():
    for model in OWNED_TABLES:
        assert issubclass(model, owned.OwnedMixin) and not model.__table__.c.owner_id.nullable
    assert access.PUBLIC_PATHS == ("/manifest.json", "/icons/")


def fake_apps(tmp_path, monkeypatch, **emails_by_folder):
    """Other apps' databases next to this one, each with the given people (see shared_python.directory)."""
    for folder, (filename, emails) in emails_by_folder.items():
        (tmp_path / folder).mkdir(exist_ok=True)
        connection = sqlite3.connect(tmp_path / folder / filename)
        connection.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT NOT NULL)")
        connection.executemany("INSERT INTO users (email) VALUES (?)", [(e,) for e in emails])
        connection.commit()
        connection.close()
    monkeypatch.setenv("PEOPLE_APPS_DIR", str(tmp_path))


def test_suggestions_are_everyone_from_any_app_minus_people_already_here(person, people, tmp_path, monkeypatch):
    fake_apps(
        tmp_path, monkeypatch,
        **{"lists": ("gifts.db", ["Zed@example.com", "bob@example.com"]), "finances": ("finances.db", ["amy@example.com"])},
    )
    resp = person(ADMIN).get("/api/users/suggestions")
    assert resp.status_code == 200
    # the administrator and Bob already have access here, so they are not offered again
    assert [x["email"] for x in resp.json()] == ["amy@example.com", "zed@example.com"]


def test_suggestions_say_who_uses_the_apps_so_only_an_administrator_gets_them(person, people, tmp_path, monkeypatch):
    fake_apps(tmp_path, monkeypatch, lists=("gifts.db", ["secret-person@example.com"]))
    resp = person("carol@example.com").get("/api/users/suggestions")
    assert resp.status_code == 403 and "secret-person" not in resp.text
