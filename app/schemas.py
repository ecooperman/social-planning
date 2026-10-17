from datetime import datetime
from typing import Optional

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
