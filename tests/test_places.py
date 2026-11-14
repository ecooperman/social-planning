"""The Google place lookup behind Settings (app/places.py and /api/locations/lookup*)."""
import pytest

from app import places


def _fake_google(monkeypatch, response):
    calls = []

    def request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return response(url) if callable(response) else response

    monkeypatch.setattr(places, "_request", lambda method, url, **kw: request(method, url, **kw))
    return calls


def test_lookup_is_unavailable_without_a_key(client):
    assert client.get("/api/locations/lookup/available").json() == {"available": False}


def test_lookup_is_available_with_a_key(client, monkeypatch):
    monkeypatch.setattr(places, "GOOGLE_MAPS_API_KEY", "k")
    assert client.get("/api/locations/lookup/available").json() == {"available": True}


def test_calls_without_a_key_fail_clearly(client):
    resp = client.get("/api/locations/lookup?q=paris")
    assert resp.status_code == 502
    assert "GOOGLE_MAPS_API_KEY" in resp.json()["detail"]


def test_a_blank_search_returns_nothing_without_calling_google(client):
    assert client.get("/api/locations/lookup?q=%20%20").json() == []


def test_autocomplete_keeps_only_place_predictions(client, monkeypatch):
    calls = _fake_google(
        monkeypatch,
        {
            "suggestions": [
                {"placePrediction": {"placeId": "p1", "text": {"text": "Paris, France"}}},
                {"queryPrediction": {"text": {"text": "paris hotels"}}},
            ]
        },
    )
    assert client.get("/api/locations/lookup?q=%20paris%20").json() == [{"place_id": "p1", "label": "Paris, France"}]
    assert calls[0][2]["json"] == {"input": "paris"}


def test_a_google_failure_is_a_502(client, monkeypatch):
    def fail(method, url, **kwargs):
        raise places.PlacesError("Google lookup failed: quota")

    monkeypatch.setattr(places, "_request", fail)
    resp = client.get("/api/locations/lookup?q=x")
    assert resp.status_code == 502
    assert "quota" in resp.json()["detail"]
    assert client.get("/api/locations/lookup/p1").status_code == 502


def _details(display, city, region_long, region_short, country_long, country_short):
    components = []
    if city:
        components.append({"types": ["locality"], "longText": city, "shortText": city})
    if region_long:
        components.append({"types": ["administrative_area_level_1"], "longText": region_long, "shortText": region_short})
    components.append({"types": ["country"], "longText": country_long, "shortText": country_short})
    return {
        "id": "pid",
        "displayName": {"text": display},
        "location": {"latitude": 1.5, "longitude": 2.5},
        "addressComponents": components,
    }


def test_us_places_are_labelled_with_the_state_abbreviation(monkeypatch):
    _fake_google(monkeypatch, _details("Salem", "Salem", "Massachusetts", "MA", "United States", "US"))
    d = places.details("pid")
    assert d.name == "Salem, MA"
    assert (d.city, d.region, d.country) == ("Salem", "Massachusetts", "United States")
    assert (d.latitude, d.longitude) == (1.5, 2.5)


def test_other_places_are_labelled_with_the_country(monkeypatch):
    _fake_google(monkeypatch, _details("Lyon", "Lyon", "Auvergne-Rhône-Alpes", "ARA", "France", "FR"))
    assert places.details("pid").name == "Lyon, France"


def test_a_place_named_like_its_country_or_region_is_not_repeated_in_its_label(monkeypatch):
    _fake_google(monkeypatch, _details("Iceland", None, None, None, "Iceland", "IS"))
    assert places.details("pid").name == "Iceland"
    # In the US/Canada/Australia a place gets its state abbreviation - unless it *is* the state.
    _fake_google(monkeypatch, _details("Massachusetts", None, "Massachusetts", "MA", "United States", "US"))
    assert places.details("pid").name == "Massachusetts, United States"
    _fake_google(monkeypatch, _details("Quebec", None, "Quebec", "QC", "Canada", "CA"))
    assert places.details("pid").name == "Quebec, Canada"


def test_a_town_filed_as_postal_town_still_gets_a_city(monkeypatch):
    data = _details("Bath", None, "England", "ENG", "United Kingdom", "GB")
    data["addressComponents"].append({"types": ["postal_town"], "longText": "Bath", "shortText": "Bath"})
    _fake_google(monkeypatch, data)
    assert places.details("pid").city == "Bath"


def test_details_point_at_records_that_already_exist(client, make_location, monkeypatch):
    loc = make_location("Salem, MA", new_country="United States", new_region="Massachusetts", new_city="Salem")
    _fake_google(monkeypatch, _details("Salem", "salem", "MASSACHUSETTS", "MA", "united states", "US"))
    body = client.get("/api/locations/lookup/pid").json()
    assert (body["country_id"], body["region_id"], body["city_id"]) == (loc.country_id, loc.region_id, loc.city_id)


def test_details_leave_ids_empty_for_new_places(client, monkeypatch):
    _fake_google(monkeypatch, _details("Lyon", "Lyon", None, None, "France", "FR"))
    body = client.get("/api/locations/lookup/pid").json()
    assert body["country_id"] is None and body["city_id"] is None
    assert body["name"] == "Lyon, France"


def test_the_request_helper_reports_google_errors(monkeypatch):
    import requests

    monkeypatch.setattr(places, "GOOGLE_MAPS_API_KEY", "k")

    class Resp:
        ok = False
        status_code = 403

        def json(self):
            return {"error": {"message": "API key invalid"}}

    monkeypatch.setattr(requests, "request", lambda *a, **k: Resp())
    with pytest.raises(places.PlacesError, match="API key invalid"):
        places._request("GET", "https://example.com")

    def down(*a, **k):
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(requests, "request", down)
    with pytest.raises(places.PlacesError, match="Couldn't reach Google"):
        places._request("GET", "https://example.com")
