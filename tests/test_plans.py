from datetime import datetime

from app.scraping import base


def test_create_and_read_a_plan(client):
    made = client.post("/api/plans", json={"name": "Sunset picnic", "description": "Bring a blanket", "url": "https://example.com/p"})
    assert made.status_code == 200
    body = made.json()
    assert body["name"] == "Sunset picnic"
    assert body["imported"] is False
    assert body["scrape_status"] == "not_started"
    assert client.get(f"/api/plans/{body['id']}").json()["description"] == "Bring a blanket"


def test_a_plan_needs_a_name(client):
    assert client.post("/api/plans", json={"description": "no name"}).status_code == 422


def test_unknown_location_is_refused_on_create_and_update(client, make_plan):
    assert client.post("/api/plans", json={"name": "x", "location_id": 999}).status_code == 400
    plan = make_plan("x")
    assert client.patch(f"/api/plans/{plan.id}", json={"location_id": 999}).status_code == 400


def test_a_plan_can_be_tagged_and_untagged(client, make_plan, make_location):
    loc = make_location("Salem, MA", new_country="United States")
    plan = make_plan("Witch museum")
    tagged = client.patch(f"/api/plans/{plan.id}", json={"location_id": loc.id}).json()
    assert tagged["location"]["name"] == "Salem, MA"
    untagged = client.patch(f"/api/plans/{plan.id}", json={"location_id": None}).json()
    assert untagged["location_id"] is None and untagged["location"] is None


def test_update_changes_only_the_fields_sent(client, make_plan):
    plan = make_plan("Old name", description="keep me", url="https://example.com/x")
    body = client.patch(f"/api/plans/{plan.id}", json={"name": "New name"}).json()
    assert body["name"] == "New name"
    assert body["description"] == "keep me"
    assert body["url"] == "https://example.com/x"


def test_a_date_can_be_set_and_cleared(client, make_plan):
    plan = make_plan("Gig")
    set_ = client.patch(f"/api/plans/{plan.id}", json={"event_date": "2026-10-17T00:00:00"}).json()
    assert set_["event_date"].startswith("2026-10-17")
    cleared = client.patch(f"/api/plans/{plan.id}", json={"event_date": None}).json()
    assert cleared["event_date"] is None


def test_missing_plans_are_404(client):
    assert client.get("/api/plans/42").status_code == 404
    assert client.patch("/api/plans/42", json={"name": "x"}).status_code == 404
    assert client.delete("/api/plans/42").status_code == 404
    assert client.post("/api/plans/42/scrape").status_code == 404


def test_delete_a_plan(client, make_plan):
    plan = make_plan("Gone soon")
    assert client.delete(f"/api/plans/{plan.id}").json() == {"ok": True}
    assert client.get(f"/api/plans/{plan.id}").status_code == 404


def test_plans_list_dated_first_then_undated_newest_first(client, make_plan, db):
    undated_old = make_plan("undated old")
    undated_new = make_plan("undated new")
    later = make_plan("later", event_date=datetime(2026, 12, 1))
    sooner = make_plan("sooner", event_date=datetime(2026, 11, 1))
    # created_at is set per row; make the two undated ones differ unambiguously.
    undated_old.created_at = datetime(2026, 1, 1)
    undated_new.created_at = datetime(2026, 6, 1)
    db.commit()
    names = [p["name"] for p in client.get("/api/plans").json()]
    assert names == ["sooner", "later", "undated new", "undated old"]


def test_plans_can_be_filtered_by_location(client, make_plan, make_location):
    a = make_location("A", new_country="X")
    b = make_location("B", new_country="X")
    make_plan("in a", location_id=a.id)
    make_plan("in b", location_id=b.id)
    make_plan("nowhere")
    assert [p["name"] for p in client.get(f"/api/plans?location_id={a.id}").json()] == ["in a"]
    assert len(client.get("/api/plans").json()) == 3


# --- scraping -----------------------------------------------------------------


def test_scrape_needs_a_url(client, make_plan):
    plan = make_plan("no url")
    resp = client.post(f"/api/plans/{plan.id}/scrape")
    assert resp.status_code == 400


def test_scrape_of_an_unsupported_site_is_recorded(client, make_plan):
    plan = make_plan("blog", url="https://blog.example.com/post")
    body = client.post(f"/api/plans/{plan.id}/scrape").json()
    assert body["scrape_status"] == "unsupported"
    assert body["scrape_error"]


def test_scrape_success_saves_the_preview(client, make_plan, monkeypatch):
    monkeypatch.setattr(
        "app.scraping.instagram.fetch_og_tags",
        lambda url: base.ScrapedContent(title="T", description="D", image_url="https://img.example.com/i.jpg"),
    )
    plan = make_plan("post", url="https://www.instagram.com/p/abc/")
    body = client.post(f"/api/plans/{plan.id}/scrape").json()
    assert body["scrape_status"] == "success"
    assert (body["scraped_title"], body["scraped_description"]) == ("T", "D")
    assert body["scraped_image_url"] == "https://img.example.com/i.jpg"
    assert body["scraped_at"]


def test_scrape_failure_is_recorded_not_raised(client, make_plan, monkeypatch):
    def boom(url):
        raise base.ScraperError("login wall")

    monkeypatch.setattr("app.scraping.facebook.fetch_og_tags", boom)
    plan = make_plan("fb", url="https://www.facebook.com/x/posts/1")
    body = client.post(f"/api/plans/{plan.id}/scrape").json()
    assert body["scrape_status"] == "failed"
    assert body["scrape_error"] == "login wall"


def test_a_later_success_clears_an_earlier_error(client, make_plan, monkeypatch):
    plan = make_plan("post", url="https://www.instagram.com/p/abc/")

    def boom(url):
        raise base.ScraperError("temporary")

    monkeypatch.setattr("app.scraping.instagram.fetch_og_tags", boom)
    assert client.post(f"/api/plans/{plan.id}/scrape").json()["scrape_status"] == "failed"

    monkeypatch.setattr("app.scraping.instagram.fetch_og_tags", lambda url: base.ScrapedContent(title="Now works"))
    body = client.post(f"/api/plans/{plan.id}/scrape").json()
    assert body["scrape_status"] == "success"
    assert body["scrape_error"] is None
    assert body["scraped_title"] == "Now works"
