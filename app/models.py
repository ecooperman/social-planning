import enum
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Enum, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from .database import Base


class ScrapeStatus(str, enum.Enum):
    not_started = "not_started"
    success = "success"
    failed = "failed"
    unsupported = "unsupported"


class Country(Base):
    """Top of the place hierarchy (country -> region -> city) that a
    Location points into. Each level is its own managed list - picked from
    a dropdown, or created in place from the location form / Google lookup -
    so a place is spelled one way and filed under the right parent
    everywhere. Names are unique ignoring case (enforced in crud)."""

    __tablename__ = "countries"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    regions = relationship("Region", back_populates="country")


class Region(Base):
    """A state/province/prefecture - always inside one country. Called
    "region" in code because most countries don't have states."""

    __tablename__ = "regions"
    __table_args__ = (UniqueConstraint("country_id", "name", name="uq_regions_country_name"),)

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    country = relationship("Country", back_populates="regions")


class City(Base):
    """Always inside one country, and inside one of its regions - except in
    a country that has no regions at all (Singapore, Monaco), where
    region_id is null. That rule is enforced when a city is created (see
    crud.resolve_place), not here, since a country can gain its first
    region after cities already exist under it."""

    __tablename__ = "cities"
    __table_args__ = (UniqueConstraint("country_id", "region_id", "name", name="uq_cities_parent_name"),)

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=False)
    region_id = Column(Integer, ForeignKey("regions.id"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    country = relationship("Country")
    region = relationship("Region")


class Location(Base):
    """A canonical place plans can be tagged with, managed on settings.html.
    Picked from a list rather than typed per plan, so "NYC" vs "New York"
    can't split one place's plans in two - which matters once
    trip-planning starts asking for "every plan in <location>".

    Where it is comes from the country -> region -> city hierarchy, at
    whatever depth fits: Salem is a city, Napa Valley only a region,
    Iceland only a country. country_id is required by the Settings form but
    nullable here, so a quick name-only location (the web-capture
    extension's "+ New location") can be filled in later.
    """

    __tablename__ = "locations"

    id = Column(Integer, primary_key=True)
    # The label shown everywhere ("Salem, MA") - unique ignoring case.
    name = Column(String, nullable=False, unique=True)

    country_id = Column(Integer, ForeignKey("countries.id"), nullable=True)
    region_id = Column(Integer, ForeignKey("regions.id"), nullable=True)
    city_id = Column(Integer, ForeignKey("cities.id"), nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    # Google's Place ID, set only by the lookup - the real "same place"
    # check (two spellings of one place can't both be added), and the
    # marker that a location was verified rather than typed.
    place_id = Column(String, nullable=True, unique=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    country = relationship("Country")
    region = relationship("Region")
    city = relationship("City")


class Plan(Base):
    __tablename__ = "plans"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    url = Column(String, nullable=True)
    event_date = Column(DateTime, nullable=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)
    # True for plans created by a bulk import (the web-capture extension's
    # Instagram collection import, routers/instagram_import.py) rather than
    # added by hand on the plans page - lets the list filter one from the
    # other. Set by the importer only; not part of PlanCreate/PlanUpdate.
    imported = Column(Boolean, nullable=False, default=False, server_default="0")
    # Imported plans only: the source post's caption, kept so a plan can be
    # re-read later without going back to Instagram.
    caption = Column(Text, nullable=True)
    # Where the caption says the place is, as Claude read it - a second
    # opinion next to location_id (which is always the location picked for
    # the whole import batch), so a Boston spot saved in a Salem collection
    # can be spotted. Plain text, not linked into the country/region/city
    # lists, since it's unverified. All null means the caption didn't say.
    parsed_city = Column(String, nullable=True)
    parsed_region = Column(String, nullable=True)
    parsed_country = Column(String, nullable=True)

    scrape_status = Column(Enum(ScrapeStatus), nullable=False, default=ScrapeStatus.not_started)
    scraped_title = Column(String, nullable=True)
    scraped_description = Column(String, nullable=True)
    scraped_image_url = Column(String, nullable=True)
    scraped_at = Column(DateTime, nullable=True)
    scrape_error = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    location = relationship("Location")
