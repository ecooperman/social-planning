import enum
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from .database import Base


class ScrapeStatus(str, enum.Enum):
    not_started = "not_started"
    success = "success"
    failed = "failed"
    unsupported = "unsupported"


class Location(Base):
    """A canonical place plans can be tagged with, managed on settings.html.
    Picked from a list rather than typed per plan, so "NYC" vs "New York"
    can't split one place's plans in two - which matters once
    trip-planning starts asking for "every plan in <location>"."""

    __tablename__ = "locations"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Plan(Base):
    __tablename__ = "plans"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    url = Column(String, nullable=True)
    event_date = Column(DateTime, nullable=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)

    scrape_status = Column(Enum(ScrapeStatus), nullable=False, default=ScrapeStatus.not_started)
    scraped_title = Column(String, nullable=True)
    scraped_description = Column(String, nullable=True)
    scraped_image_url = Column(String, nullable=True)
    scraped_at = Column(DateTime, nullable=True)
    scrape_error = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    location = relationship("Location")
