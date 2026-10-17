from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from .models import ScrapeStatus


class LocationBase(BaseModel):
    name: str


class LocationCreate(LocationBase):
    pass


class LocationUpdate(BaseModel):
    name: Optional[str] = None


class Location(LocationBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


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
