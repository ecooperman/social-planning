"""The proxy to trip-planning (routers/trips_link.py) - every call is faked."""
import requests

from app.routers import trips_link


class _Resp:
    def __init__(self, data=None, status=200):
        self._data, self.status_code = data, status
        self.ok = 200 <= status < 300

    def json(self):
        if self._data is None:
            raise ValueError("no body")
        return self._data


def _fake(monkeypatch, resp):
    seen = []

    def request(method, url, **kwargs):
        seen.append((method, url, kwargs))
        return resp

    monkeypatch.setattr(requests, "request", request)
    return seen


def test_the_trip_picker_lists_only_active_trips(client, monkeypatch):
    seen = _fake(
        monkeypatch,
        _Resp([{"id": 1, "location": "Paris", "archived": False, "x": 1}, {"id": 2, "location": "Old", "archived": True}, {"id": 3, "location": "Rome"}]),
    )
    assert client.get("/api/trips-link/trips").json() == [{"id": 1, "location": "Paris"}, {"id": 3, "location": "Rome"}]
    assert seen[0][0:2] == ("GET", "http://127.0.0.1:8060/api/trips")


def test_links_come_with_the_public_trips_url(client, monkeypatch):
    _fake(monkeypatch, _Resp([{"plan_id": 5, "trip_location": "Paris"}]))
    body = client.get("/api/trips-link/links").json()
    assert body["links"] == [{"plan_id": 5, "trip_location": "Paris"}]
    assert body["trips_url"] == trips_link.TRIPS_PUBLIC_URL


def test_send_posts_the_plan_to_the_import_endpoint(client, monkeypatch):
    seen = _fake(monkeypatch, _Resp({"created": 1}))
    assert client.post("/api/trips-link/send", json={"plan_id": 7, "trip_id": 3}).json() == {"created": 1}
    method, url, kwargs = seen[0]
    assert (method, url) == ("POST", "http://127.0.0.1:8060/api/plan-links/import")
    assert kwargs["json"] == {"plan_ids": [7], "trip_id": 3}


def test_send_without_a_trip_makes_an_unassigned_activity(client, monkeypatch):
    seen = _fake(monkeypatch, _Resp({}))
    client.post("/api/trips-link/send", json={"plan_id": 7})
    assert seen[0][2]["json"] == {"plan_ids": [7], "trip_id": None}


def test_the_service_token_is_sent_when_configured(client, monkeypatch):
    monkeypatch.setattr(trips_link, "TRIPS_SERVICE_TOKEN", "s3cret")
    seen = _fake(monkeypatch, _Resp([]))
    client.get("/api/trips-link/trips")
    assert seen[0][2]["headers"]["X-Service-Token"] == "s3cret"


def test_no_token_means_no_header(client, monkeypatch):
    seen = _fake(monkeypatch, _Resp([]))
    client.get("/api/trips-link/trips")
    assert "headers" not in seen[0][2]


def test_an_unreachable_trips_app_is_a_502(client, monkeypatch):
    def down(*a, **k):
        raise requests.ConnectionError("refused")

    monkeypatch.setattr(requests, "request", down)
    resp = client.get("/api/trips-link/trips")
    assert resp.status_code == 502
    assert "Couldn't reach the trips app" in resp.json()["detail"]


def test_a_4xx_from_trips_is_passed_through(client, monkeypatch):
    _fake(monkeypatch, _Resp({"detail": "Trip not found"}, status=404))
    resp = client.post("/api/trips-link/send", json={"plan_id": 1, "trip_id": 99})
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Trip not found"


def test_a_5xx_or_unreadable_error_is_a_502(client, monkeypatch):
    _fake(monkeypatch, _Resp({"detail": "boom"}, status=500))
    assert client.get("/api/trips-link/trips").status_code == 502
    _fake(monkeypatch, _Resp(None, status=503))
    resp = client.get("/api/trips-link/trips")
    assert resp.status_code == 502
    assert "503" in resp.json()["detail"]
