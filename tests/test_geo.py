"""The country / region / city lists behind locations (Settings > Countries, states & cities)."""


def _loc(client, name, **place):
    return client.post("/api/locations", json={"name": name, **place}).json()


def test_lists_filter_by_parent(client):
    _loc(client, "Montreal", new_country="Canada", new_region="Quebec", new_city="Montreal")
    _loc(client, "Boston", new_country="United States", new_region="Massachusetts", new_city="Boston")
    canada = next(c for c in client.get("/api/countries").json() if c["name"] == "Canada")
    assert [r["name"] for r in client.get(f"/api/regions?country_id={canada['id']}").json()] == ["Quebec"]
    assert [c["name"] for c in client.get(f"/api/cities?country_id={canada['id']}").json()] == ["Montreal"]
    assert len(client.get("/api/cities").json()) == 2


def test_cities_directly_under_a_country_can_be_listed(client):
    _loc(client, "Singapore", new_country="Singapore", new_city="Singapore")
    _loc(client, "Montreal", new_country="Canada", new_region="Quebec", new_city="Montreal")
    direct = client.get("/api/cities?no_region=true").json()
    assert [c["name"] for c in direct] == ["Singapore"]


def test_rename_each_level(client):
    made = _loc(client, "Montreal", new_country="Canada", new_region="Quebec", new_city="Montreal")
    assert client.patch(f"/api/countries/{made['country_id']}", json={"name": "CA"}).json()["name"] == "CA"
    assert client.patch(f"/api/regions/{made['region_id']}", json={"name": "QC"}).json()["name"] == "QC"
    assert client.patch(f"/api/cities/{made['city_id']}", json={"name": "MTL"}).json()["name"] == "MTL"
    # A location shows the corrected spelling everywhere.
    refreshed = client.get("/api/locations").json()[0]
    assert (refreshed["country"]["name"], refreshed["region"]["name"], refreshed["city"]["name"]) == ("CA", "QC", "MTL")


def test_rename_is_trimmed_and_needs_a_name(client):
    made = _loc(client, "X", new_country="Canada")
    ok = client.patch(f"/api/countries/{made['country_id']}", json={"name": "  Kanada "})
    assert ok.json()["name"] == "Kanada"
    assert client.patch(f"/api/countries/{made['country_id']}", json={"name": " "}).status_code == 400


def test_rename_cannot_duplicate_a_sibling_ignoring_case(client):
    _loc(client, "A", new_country="Canada")
    b = _loc(client, "B", new_country="France")
    assert client.patch(f"/api/countries/{b['country_id']}", json={"name": "canada"}).status_code == 409


def test_the_same_region_name_is_fine_in_different_countries(client):
    us = _loc(client, "A", new_country="United States", new_region="Georgia")
    ge = _loc(client, "B", new_country="Georgia")
    assert client.patch(f"/api/countries/{ge['country_id']}", json={"name": "Georgia"}).status_code == 200
    assert us["region"]["name"] == "Georgia"


def test_renaming_something_to_its_own_name_is_fine(client):
    made = _loc(client, "X", new_country="Canada")
    assert client.patch(f"/api/countries/{made['country_id']}", json={"name": "Canada"}).status_code == 200


def test_missing_records_are_404(client):
    for kind in ("countries", "regions", "cities"):
        assert client.patch(f"/api/{kind}/99", json={"name": "x"}).status_code == 404
        assert client.delete(f"/api/{kind}/99").status_code == 404


def test_delete_only_when_nothing_uses_it(client):
    made = _loc(client, "Montreal", new_country="Canada", new_region="Quebec", new_city="Montreal")
    # Everything is in use: the city and region by the location / child, the country by both.
    assert client.delete(f"/api/cities/{made['city_id']}").status_code == 409
    assert client.delete(f"/api/regions/{made['region_id']}").status_code == 409
    assert client.delete(f"/api/countries/{made['country_id']}").status_code == 409
    client.delete(f"/api/locations/{made['id']}")
    # Now they can go, bottom-up - the country still holds the region until it is deleted first.
    assert client.delete(f"/api/countries/{made['country_id']}").status_code == 409
    assert client.delete(f"/api/cities/{made['city_id']}").json() == {"ok": True}
    assert client.delete(f"/api/regions/{made['region_id']}").json() == {"ok": True}
    assert client.delete(f"/api/countries/{made['country_id']}").json() == {"ok": True}
