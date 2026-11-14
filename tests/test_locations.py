import pytest

from app import models


def _place(client, **fields):
    return client.post("/api/locations", json=fields)


def test_a_location_with_new_country_region_and_city_builds_the_hierarchy(client):
    resp = _place(client, name="Montreal", new_country="Canada", new_region="Quebec", new_city="Montreal")
    assert resp.status_code == 200
    body = resp.json()
    assert (body["country"]["name"], body["region"]["name"], body["city"]["name"]) == ("Canada", "Quebec", "Montreal")
    assert body["city"]["region_id"] == body["region"]["id"]
    assert body["region"]["country_id"] == body["country"]["id"]


def test_a_second_location_reuses_places_ignoring_case(client):
    first = _place(client, name="Montreal", new_country="Canada", new_region="Quebec", new_city="Montreal").json()
    second = _place(client, name="Quebec City", new_country="canada", new_region="QUEBEC", new_city="Quebec City").json()
    assert second["country_id"] == first["country_id"]
    assert second["region_id"] == first["region_id"]
    assert len(client.get("/api/countries").json()) == 1
    assert len(client.get("/api/regions").json()) == 1


def test_a_location_can_stop_at_any_depth(client):
    iceland = _place(client, name="Iceland", new_country="Iceland").json()
    assert iceland["region"] is None and iceland["city"] is None
    bare = _place(client, name="Somewhere").json()
    assert bare["country_id"] is None


def test_names_are_unique_ignoring_case_and_trimmed(client):
    assert _place(client, name="Tokyo").status_code == 200
    assert _place(client, name="  tokyo ").status_code == 409


def test_a_blank_name_is_refused(client):
    resp = _place(client, name="   ")
    assert resp.status_code == 400


def test_a_google_place_can_only_be_added_once(client):
    assert _place(client, name="Paris", place_id="ChIJ-paris").status_code == 200
    resp = _place(client, name="Paris, France", place_id="ChIJ-paris")
    assert resp.status_code == 409
    assert "Paris" in resp.json()["detail"]


def test_a_city_needs_a_country(client):
    assert _place(client, name="x", new_city="Lyon").status_code == 400


def test_a_city_in_a_country_with_regions_needs_one(client):
    _place(client, name="Montreal", new_country="Canada", new_region="Quebec", new_city="Montreal")
    resp = _place(client, name="Toronto", new_country="Canada", new_city="Toronto")
    assert resp.status_code == 400
    assert "Canada" in resp.json()["detail"]


def test_a_country_without_regions_can_hold_a_city_directly(client):
    resp = _place(client, name="Singapore", new_country="Singapore", new_city="Singapore")
    assert resp.status_code == 200
    assert resp.json()["region"] is None


def test_a_region_must_belong_to_the_chosen_country(client):
    quebec = _place(client, name="Montreal", new_country="Canada", new_region="Quebec").json()
    france = _place(client, name="Paris", new_country="France").json()
    resp = _place(client, name="Bad", country_id=france["country_id"], region_id=quebec["region_id"])
    assert resp.status_code == 400


def test_an_unknown_country_id_is_refused(client):
    assert _place(client, name="x", country_id=999).status_code == 400


def test_a_failed_save_leaves_no_half_built_places(client):
    # The country would be created before the city fails - it must be rolled back.
    resp = _place(client, name="Bad", new_country="Narnia", new_city="Cair Paravel", region_id=999)
    assert resp.status_code == 400
    assert client.get("/api/countries").json() == []


def test_list_is_sorted_ignoring_case(client):
    for name in ("banana", "Apple", "cherry"):
        _place(client, name=name)
    assert [l["name"] for l in client.get("/api/locations").json()] == ["Apple", "banana", "cherry"]


def test_rename_a_location_keeps_its_place(client):
    made = _place(client, name="NYC", new_country="United States", new_region="New York", new_city="New York").json()
    body = client.patch(f"/api/locations/{made['id']}", json={"name": "New York City"}).json()
    assert body["name"] == "New York City"
    assert body["city"]["name"] == "New York"


def test_rename_cannot_collide_with_another_location(client):
    _place(client, name="A")
    b = _place(client, name="B").json()
    assert client.patch(f"/api/locations/{b['id']}", json={"name": "a"}).status_code == 409


def test_saving_a_location_under_its_own_name_is_fine(client):
    a = _place(client, name="A").json()
    assert client.patch(f"/api/locations/{a['id']}", json={"name": "A"}).status_code == 200


def test_the_place_can_be_changed_on_update(client):
    made = _place(client, name="X", new_country="Canada", new_region="Quebec").json()
    body = client.patch(f"/api/locations/{made['id']}", json={"new_country": "France"}).json()
    assert body["country"]["name"] == "France"
    assert body["region"] is None  # a region from the old country does not carry over


def test_update_of_a_missing_location_is_404(client):
    assert client.patch("/api/locations/9", json={"name": "x"}).status_code == 404


def test_delete_works_until_a_plan_uses_it(client, make_plan):
    loc = _place(client, name="Used").json()
    plan = make_plan("p", location_id=loc["id"])
    resp = client.delete(f"/api/locations/{loc['id']}")
    assert resp.status_code == 409
    client.delete(f"/api/plans/{plan.id}")
    assert client.delete(f"/api/locations/{loc['id']}").json() == {"ok": True}
    assert client.delete(f"/api/locations/{loc['id']}").status_code == 404


def test_the_geo_lists_are_left_behind_when_a_location_is_deleted(client):
    loc = _place(client, name="X", new_country="Canada").json()
    client.delete(f"/api/locations/{loc['id']}")
    assert len(client.get("/api/countries").json()) == 1  # managed separately on the Settings page
