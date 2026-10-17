"""Google Places API (New) lookups behind settings.html's location search -
autocomplete while typing, then full details for the picked suggestion,
shaped into Location fields. Optional by design: with no key, or if Google
errors, the page falls back to typing the fields in by hand.
"""
from typing import List, Optional

import requests

from . import schemas
from .config import GOOGLE_MAPS_API_KEY

AUTOCOMPLETE_URL = "https://places.googleapis.com/v1/places:autocomplete"
DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"
DETAILS_FIELDS = "id,displayName,location,addressComponents"

# Where the state/province reads naturally as its abbreviation ("Salem,
# MA"); everywhere else the default label uses the country ("Kyoto, Japan").
_SHORT_REGION_COUNTRIES = {"US", "CA", "AU"}


class PlacesError(Exception):
    pass


def available() -> bool:
    return bool(GOOGLE_MAPS_API_KEY)


def _request(method: str, url: str, **kwargs) -> dict:
    if not GOOGLE_MAPS_API_KEY:
        raise PlacesError("GOOGLE_MAPS_API_KEY is not configured")
    headers = {"X-Goog-Api-Key": GOOGLE_MAPS_API_KEY, **kwargs.pop("headers", {})}
    try:
        resp = requests.request(method, url, headers=headers, timeout=8, **kwargs)
    except requests.RequestException as exc:
        raise PlacesError(f"Couldn't reach Google: {exc}")
    if not resp.ok:
        # Google's own message is the useful part, e.g. "Places API (New)
        # has not been used in project ... or it is disabled".
        try:
            message = resp.json()["error"]["message"]
        except (ValueError, KeyError, TypeError):
            message = f"HTTP {resp.status_code}"
        raise PlacesError(f"Google lookup failed: {message}")
    return resp.json()


def autocomplete(query: str) -> List[schemas.PlaceSuggestion]:
    data = _request("POST", AUTOCOMPLETE_URL, json={"input": query})
    suggestions = []
    for item in data.get("suggestions", []):
        prediction = item.get("placePrediction")
        if not prediction:
            continue
        suggestions.append(
            schemas.PlaceSuggestion(place_id=prediction["placeId"], label=prediction["text"]["text"])
        )
    return suggestions


def _component(components: list, kind: str) -> Optional[dict]:
    return next((c for c in components if kind in c.get("types", [])), None)


def details(place_id: str) -> schemas.PlaceDetails:
    data = _request(
        "GET",
        DETAILS_URL.format(place_id=place_id),
        headers={"X-Goog-FieldMask": DETAILS_FIELDS},
    )
    components = data.get("addressComponents", [])
    city = _component(components, "locality") or _component(components, "postal_town")
    region = _component(components, "administrative_area_level_1")
    country = _component(components, "country")
    display = (data.get("displayName") or {}).get("text") or (city or {}).get("longText") or place_id

    if region and country and country.get("shortText") in _SHORT_REGION_COUNTRIES and region["longText"] != display:
        label = f"{display}, {region['shortText']}"
    elif country and country["longText"] != display:
        label = f"{display}, {country['longText']}"
    else:
        label = display

    location = data.get("location") or {}
    return schemas.PlaceDetails(
        place_id=data.get("id", place_id),
        name=label,
        city=city["longText"] if city else None,
        region=region["longText"] if region else None,
        country=country["longText"] if country else None,
        latitude=location.get("latitude"),
        longitude=location.get("longitude"),
    )
