"""The Instagram collection import (routers/instagram_import.py). Claude is faked: each test
says what it "read" from a caption via the `reads` fixture."""
import pytest

from app import ai_extraction
from app.ai_extraction import ExtractedPlace
from app.routers import instagram_import as imp


def place(name, notes="", city=None, region=None, country=None):
    return ExtractedPlace(name=name, notes=notes, city=city, region=region, country=country)


@pytest.fixture()
def reads(monkeypatch):
    """reads({"caption text": [place, ...]}) - what the fake Claude returns per caption; anything
    unlisted is "not a place". `reads.calls` records (caption, filed_under) for each call."""
    table, calls = {}, []

    def extract(caption, filed_under=None):
        calls.append((caption, filed_under))
        return table.get(caption, [])

    monkeypatch.setattr(ai_extraction, "extract_places", extract)

    def setter(mapping):
        table.update(mapping)

    setter.calls = calls
    return setter


def run(client, posts, **extra):
    body = {"posts": [{"permalink": p, "caption": c} for p, c in posts], **extra}
    return client.post("/api/instagram-import", json=body)


# --- permalinks -------------------------------------------------------------------


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.instagram.com/p/ABC123/?img_index=1", "https://www.instagram.com/p/ABC123/"),
        ("https://www.instagram.com/someuser/reel/XYZ/", "https://www.instagram.com/reel/XYZ/"),
        ("https://instagram.com/p/ABC123", "https://www.instagram.com/p/ABC123/"),
        ("https://example.com/not-instagram", "https://example.com/not-instagram"),
    ],
)
def test_permalinks_are_reduced_to_one_shape(url, expected):
    assert imp._canonical_permalink(url) == expected


def test_the_batch_location_is_described_with_its_place_hierarchy(make_location):
    loc = make_location("Salem, MA", new_country="United States", new_region="Massachusetts", new_city="Salem")
    assert imp._describe_location(loc) == "Salem, MA (Salem, Massachusetts, United States)"
    assert imp._describe_location(make_location("Somewhere")) == "Somewhere"


# --- importing --------------------------------------------------------------------


def test_each_place_found_becomes_an_imported_plan(client, reads):
    reads({"Top spots": [place("Cafe A", "Great latte", city="Boston", region="Massachusetts", country="United States"), place("Shop B")]})
    body = run(client, [("https://www.instagram.com/p/AAA/?utm=1", "Top spots")]).json()
    assert body["plans_created"] == 2 and body["created_names"] == ["Cafe A", "Shop B"]
    plans = client.get("/api/plans").json()
    cafe = next(p for p in plans if p["name"] == "Cafe A")
    assert cafe["imported"] is True
    assert cafe["url"] == "https://www.instagram.com/p/AAA/"  # canonical
    assert cafe["description"] == "Great latte"
    assert cafe["caption"] == "Top spots"
    assert (cafe["parsed_city"], cafe["parsed_region"], cafe["parsed_country"]) == ("Boston", "Massachusetts", "United States")
    shop = next(p for p in plans if p["name"] == "Shop B")
    assert shop["description"] is None and shop["parsed_city"] is None


def test_captions_that_are_not_places_are_skipped(client, reads):
    body = run(client, [("https://www.instagram.com/p/MEME/", "lol")]).json()
    assert (body["posts_processed"], body["posts_skipped"], body["plans_created"]) == (1, 1, 0)
    assert client.get("/api/plans").json() == []


def test_the_batch_location_is_applied_and_given_to_claude(client, reads, make_location):
    loc = make_location("Salem, MA", new_country="United States", new_region="Massachusetts", new_city="Salem")
    reads({"c": [place("Museum")]})
    run(client, [("https://www.instagram.com/p/A/", "c")], location_id=loc.id)
    assert client.get("/api/plans").json()[0]["location_id"] == loc.id
    assert reads.calls == [("c", "Salem, MA (Salem, Massachusetts, United States)")]


def test_an_unknown_batch_location_is_refused_before_any_work(client, reads):
    reads({"c": [place("X")]})
    assert run(client, [("https://www.instagram.com/p/A/", "c")], location_id=99).status_code == 400
    assert reads.calls == []


def test_posts_already_imported_are_skipped_without_calling_claude(client, reads):
    reads({"c": [place("X")]})
    run(client, [("https://www.instagram.com/p/A/", "c")])
    reads.calls.clear()
    body = run(client, [("https://www.instagram.com/reel/A/", "c"), ("https://www.instagram.com/p/A/?x=1", "c")]).json()
    # The first has a different kind (reel) so it is a new post; the second is the same permalink.
    assert body["posts_already_imported"] == 1
    assert body["plans_created"] == 1
    assert len(reads.calls) == 1


def test_the_same_post_twice_in_one_batch_is_imported_once(client, reads):
    reads({"c": [place("X")]})
    body = run(client, [("https://www.instagram.com/p/A/", "c"), ("https://www.instagram.com/p/A/?dup=1", "c")]).json()
    assert body["plans_created"] == 1 and body["posts_already_imported"] == 1


def test_a_missing_api_key_fails_the_import_loudly(client, monkeypatch):
    def no_key(caption, filed_under=None):
        raise RuntimeError("ANTHROPIC_API_KEY is not configured")

    monkeypatch.setattr(ai_extraction, "extract_places", no_key)
    resp = run(client, [("https://www.instagram.com/p/A/", "c")])
    assert resp.status_code == 503
    assert "ANTHROPIC_API_KEY" in resp.json()["detail"]


# --- re-checking posts already imported ---------------------------------------------


def test_recheck_refreshes_parsed_locations_but_never_adds_plans(client, reads):
    reads({"old": [place("Cafe A")]})
    run(client, [("https://www.instagram.com/p/A/", "old")])
    reads({"new caption": [place("cafe a", city="Montreal", region="Quebec", country="Canada"), place("Brand new place")]})
    body = run(client, [("https://www.instagram.com/p/A/", "new caption")], recheck_existing=True).json()
    assert (body["posts_rechecked"], body["plans_updated"], body["plans_created"]) == (1, 1, 0)
    plans = client.get("/api/plans").json()
    assert len(plans) == 1
    assert plans[0]["name"] == "Cafe A"  # the name the person may have edited is untouched
    assert (plans[0]["parsed_city"], plans[0]["caption"]) == ("Montreal", "new caption")


def test_recheck_pairs_a_reworded_name_when_the_counts_match(client, reads):
    reads({"c": [place("Wonder Pens")]})
    run(client, [("https://www.instagram.com/p/A/", "c")])
    reads({"c2": [place("Wonderpens", city="Toronto")]})
    body = run(client, [("https://www.instagram.com/p/A/", "c2")], recheck_existing=True).json()
    assert body["plans_updated"] == 1
    assert client.get("/api/plans").json()[0]["parsed_city"] == "Toronto"


def test_recheck_leaves_unpaired_plans_alone_but_updates_their_caption(client, reads):
    reads({"c": [place("One"), place("Two")]})
    run(client, [("https://www.instagram.com/p/A/", "c")])
    reads({"c2": [place("One", city="Paris")]})
    run(client, [("https://www.instagram.com/p/A/", "c2")], recheck_existing=True)
    plans = {p["name"]: p for p in client.get("/api/plans").json()}
    assert plans["One"]["parsed_city"] == "Paris"
    assert plans["Two"]["parsed_city"] is None
    assert plans["Two"]["caption"] == "c2"


def test_pairing_prefers_names_then_falls_back_to_order():
    class P:
        def __init__(self, name):
            self.name = name

    plans = [P("A"), P("B")]
    pairs, left = imp._pair_places(plans, [place("b"), place("a")])
    assert [(p.name, q.name) for p, q in pairs] == [("B", "b"), ("A", "a")] and left == []
    pairs, left = imp._pair_places([P("x")], [place("y")])
    assert [(p.name, q.name) for p, q in pairs] == [("x", "y")]
    pairs, left = imp._pair_places([P("x"), P("y")], [place("z")])  # counts differ: do not guess
    assert pairs == [] and [p.name for p in left] == ["x", "y"]


# --- the location check shown on the plans page -------------------------------------


def test_a_blank_parsed_location_is_stored_as_unknown(db, make_plan):
    from app import crud

    plan = make_plan("x")
    crud.set_parsed_location(db, plan, "cap", city="  ", region=None, country=" Canada ")
    assert (plan.parsed_city, plan.parsed_region, plan.parsed_country) == (None, None, "Canada")
