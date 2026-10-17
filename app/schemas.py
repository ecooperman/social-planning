from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from .models import ScrapeStatus


class Country(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


class Region(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    country_id: int


class City(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    country_id: int
    region_id: Optional[int] = None


class Rename(BaseModel):
    name: str


# The fields that say where a location is. Each level is either an existing
# record (*_id) or a name to find-or-create under the level above (new_*) -
# which is how the location form's "+ New country/state/city" options and
# the Google lookup both save in one request. See crud.resolve_place.
PLACE_FIELDS = ("country_id", "new_country", "region_id", "new_region", "city_id", "new_city")


class LocationSave(BaseModel):
    name: str
    country_id: Optional[int] = None
    new_country: Optional[str] = None
    region_id: Optional[int] = None
    new_region: Optional[str] = None
    city_id: Optional[int] = None
    new_city: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    place_id: Optional[str] = None


class LocationCreate(LocationSave):
    pass


class LocationUpdate(LocationSave):
    # Everything optional on update; sending any of PLACE_FIELDS re-resolves
    # the whole country/region/city set from what was sent.
    name: Optional[str] = None


class Location(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    country_id: Optional[int] = None
    region_id: Optional[int] = None
    city_id: Optional[int] = None
    country: Optional[Country] = None
    region: Optional[Region] = None
    city: Optional[City] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    place_id: Optional[str] = None


class PlaceSuggestion(BaseModel):
    """One autocomplete result from the Google place lookup - just enough
    to show in a list; picking one fetches the full details."""

    place_id: str
    label: str


class PlaceDetails(BaseModel):
    """A looked-up place, shaped like the location form it fills in. The
    *_id fields are the existing country/region/city records the names
    matched (ignoring case), if any - the form selects those, and offers
    the rest as "+ New" prefilled with the name."""

    place_id: str
    name: str
    city: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None
    country_id: Optional[int] = None
    region_id: Optional[int] = None
    city_id: Optional[int] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class PlanBase(BaseModel):
    name: str
    description: Optional[str] = None
    url: Optional[str] = None
    event_date: Optional[datetime] = None
    location_id: Optional[int] = None


class PlanCreate(PlanBase):
    pass


class PlanUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    url: Optional[str] = None
    event_date: Optional[datetime] = None
    location_id: Optional[int] = None


class Plan(PlanBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    location: Optional[Location] = None
    imported: bool = False
    scrape_status: ScrapeStatus
    scraped_title: Optional[str] = None
    scraped_description: Optional[str] = None
    scraped_image_url: Optional[str] = None
    scraped_at: Optional[datetime] = None
    scrape_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Instagram import (see routers/instagram_import.py)
# ---------------------------------------------------------------------------


class InstagramPost(BaseModel):
    """One saved post as read from a collection's grid page by the
    web-capture extension - just what's passively present in the page the
    human is already looking at, no extra navigation."""

    permalink: str
    caption: str
    thumbnail_url: Optional[str] = None


class InstagramImportRequest(BaseModel):
    posts: List[InstagramPost]
    # One location for the whole batch (a collection is usually one place),
    # picked from the managed list - optional, plans can be tagged later.
    location_id: Optional[int] = None


class InstagramImportResult(BaseModel):
    posts_processed: int
    # Captions Claude found no visitable place in.
    posts_skipped: int
    # Posts that already have plans from an earlier import of this
    # collection - not re-sent to Claude, so re-importing a growing
    # collection only pays for the new posts.
    posts_already_imported: int
    plans_created: int
    created_names: List[str]
