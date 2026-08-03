from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from .models import ScrapeStatus


class IdeaBase(BaseModel):
    name: str
    description: Optional[str] = None
    url: Optional[str] = None
    event_date: Optional[datetime] = None


class IdeaCreate(IdeaBase):
    pass


class IdeaUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    url: Optional[str] = None
    event_date: Optional[datetime] = None


class Idea(IdeaBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scrape_status: ScrapeStatus
    scraped_title: Optional[str] = None
    scraped_description: Optional[str] = None
    scraped_image_url: Optional[str] = None
    scraped_at: Optional[datetime] = None
    scrape_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime
