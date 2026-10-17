from datetime import datetime
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from . import models, schemas


def get_locations(db: Session):
    return db.query(models.Location).order_by(func.lower(models.Location.name)).all()


def get_location(db: Session, location_id: int):
    return db.query(models.Location).filter(models.Location.id == location_id).first()


def get_location_by_place_id(db: Session, place_id: str):
    return db.query(models.Location).filter(models.Location.place_id == place_id).first()


def location_name_taken(db: Session, name: str, exclude_id: Optional[int] = None) -> bool:
    """Case-insensitive, so "tokyo" can't sit alongside "Tokyo" - the whole
    point of a picked-from-a-list location is one spelling per place."""
    query = db.query(models.Location).filter(func.lower(models.Location.name) == name.lower())
    if exclude_id is not None:
        query = query.filter(models.Location.id != exclude_id)
    return query.first() is not None


class PlaceError(ValueError):
    """A country/region/city combination that doesn't fit the hierarchy -
    the message is shown to the user as-is."""


def _find_by_name(db: Session, model, name: str, **parents):
    query = db.query(model).filter(func.lower(model.name) == name.strip().lower())
    for column, value in parents.items():
        query = query.filter(getattr(model, column).is_(None) if value is None else getattr(model, column) == value)
    return query.first()


def find_country(db: Session, name: str):
    return _find_by_name(db, models.Country, name)


def find_region(db: Session, country_id: int, name: str):
    return _find_by_name(db, models.Region, name, country_id=country_id)


def find_city(db: Session, country_id: int, region_id: Optional[int], name: str):
    return _find_by_name(db, models.City, name, country_id=country_id, region_id=region_id)


def _find_or_create(db: Session, model, name: str, **parents):
    existing = _find_by_name(db, model, name, **parents)
    if existing is not None:
        return existing
    created = model(name=name.strip(), **parents)
    db.add(created)
    db.flush()
    return created


def resolve_place(db: Session, data: dict):
    """Turns a location form's place fields (an existing *_id or a new_*
    name per level - see schemas.PLACE_FIELDS) into (country, region,
    city), creating any new records under the right parent. A new_* name
    that matches an existing record ignoring case reuses it rather than
    duplicating it. Flushes but doesn't commit - the caller commits along
    with the location, or rolls back on PlaceError."""
    country = region = city = None

    if data.get("new_country") and data["new_country"].strip():
        country = _find_or_create(db, models.Country, data["new_country"])
    elif data.get("country_id"):
        country = db.get(models.Country, data["country_id"])
        if country is None:
            raise PlaceError("Unknown country")

    wants_region = bool((data.get("new_region") or "").strip() or data.get("region_id"))
    wants_city = bool((data.get("new_city") or "").strip() or data.get("city_id"))
    if (wants_region or wants_city) and country is None:
        raise PlaceError("Pick a country first")

    if data.get("new_region") and data["new_region"].strip():
        region = _find_or_create(db, models.Region, data["new_region"], country_id=country.id)
    elif data.get("region_id"):
        region = db.get(models.Region, data["region_id"])
        if region is None or region.country_id != country.id:
            raise PlaceError("That state/region isn't in the chosen country")

    if data.get("new_city") and data["new_city"].strip():
        if region is None and db.query(models.Region).filter(models.Region.country_id == country.id).count():
            raise PlaceError(f"Pick a state/region for this city - {country.name} has them")
        city = _find_or_create(
            db, models.City, data["new_city"], country_id=country.id, region_id=region.id if region else None
        )
    elif data.get("city_id"):
        city = db.get(models.City, data["city_id"])
        if city is None or city.country_id != country.id:
            raise PlaceError("That city isn't in the chosen country")
        if city.region_id and region is None:
            region = city.region
        if (region.id if region else None) != city.region_id:
            raise PlaceError("That city isn't in the chosen state/region")

    return country, region, city


def _apply_place(db: Session, db_location, data: dict):
    country, region, city = resolve_place(db, data)
    db_location.country_id = country.id if country else None
    db_location.region_id = region.id if region else None
    db_location.city_id = city.id if city else None


def create_location(db: Session, location: schemas.LocationCreate):
    data = location.model_dump()
    db_location = models.Location(
        name=data["name"],
        latitude=data["latitude"],
        longitude=data["longitude"],
        place_id=data["place_id"],
    )
    try:
        _apply_place(db, db_location, data)
    except PlaceError:
        db.rollback()
        raise
    db.add(db_location)
    db.commit()
    db.refresh(db_location)
    return db_location


def update_location(db: Session, location_id: int, updates: schemas.LocationUpdate):
    db_location = get_location(db, location_id)
    if db_location is None:
        return None
    data = updates.model_dump(exclude_unset=True)
    try:
        if any(field in data for field in schemas.PLACE_FIELDS):
            _apply_place(db, db_location, data)
    except PlaceError:
        db.rollback()
        raise
    for field in ("name", "latitude", "longitude", "place_id"):
        if field in data:
            setattr(db_location, field, data[field])
    db.commit()
    db.refresh(db_location)
    return db_location


def delete_location(db: Session, location_id: int) -> str:
    db_location = get_location(db, location_id)
    if db_location is None:
        return "not_found"
    if db.query(models.Plan).filter(models.Plan.location_id == location_id).count() > 0:
        return "in_use"
    db.delete(db_location)
    db.commit()
    return "deleted"


def get_plans(db: Session, location_id: Optional[int] = None):
    query = db.query(models.Plan)
    if location_id is not None:
        query = query.filter(models.Plan.location_id == location_id)
    return query.order_by(
        models.Plan.event_date.is_(None), models.Plan.event_date, models.Plan.created_at.desc()
    ).all()


def get_plan(db: Session, plan_id: int):
    return db.query(models.Plan).filter(models.Plan.id == plan_id).first()


def create_plan(db: Session, plan: schemas.PlanCreate):
    db_plan = models.Plan(**plan.model_dump())
    db.add(db_plan)
    db.commit()
    db.refresh(db_plan)
    return db_plan


def update_plan(db: Session, plan_id: int, updates: schemas.PlanUpdate):
    db_plan = get_plan(db, plan_id)
    if db_plan is None:
        return None
    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(db_plan, field, value)
    db.commit()
    db.refresh(db_plan)
    return db_plan


def delete_plan(db: Session, plan_id: int) -> bool:
    db_plan = get_plan(db, plan_id)
    if db_plan is None:
        return False
    db.delete(db_plan)
    db.commit()
    return True


def save_scrape_result(
    db: Session,
    plan_id: int,
    status: models.ScrapeStatus,
    title: Optional[str] = None,
    description: Optional[str] = None,
    image_url: Optional[str] = None,
    error: Optional[str] = None,
):
    db_plan = get_plan(db, plan_id)
    if db_plan is None:
        return None
    db_plan.scrape_status = status
    db_plan.scraped_title = title
    db_plan.scraped_description = description
    db_plan.scraped_image_url = image_url
    db_plan.scrape_error = error
    db_plan.scraped_at = datetime.utcnow()
    db.commit()
    db.refresh(db_plan)
    return db_plan


def get_plan_urls(db: Session) -> set:
    """Every plan URL in the database - the Instagram import's "already
    imported this post?" check, done once per import rather than per post."""
    return {url for (url,) in db.query(models.Plan.url).filter(models.Plan.url.isnot(None))}


# --- countries / regions / cities (Settings page lists) ------------------------
#
# Created only through a location save (resolve_place) - these are just
# for fixing a spelling or removing an unused entry afterward.


def get_countries(db: Session):
    return db.query(models.Country).order_by(func.lower(models.Country.name)).all()


def get_regions(db: Session, country_id: Optional[int] = None):
    query = db.query(models.Region)
    if country_id is not None:
        query = query.filter(models.Region.country_id == country_id)
    return query.order_by(func.lower(models.Region.name)).all()


def get_cities(db: Session, country_id: Optional[int] = None, region_id: Optional[int] = None, no_region: bool = False):
    query = db.query(models.City)
    if country_id is not None:
        query = query.filter(models.City.country_id == country_id)
    if no_region:
        query = query.filter(models.City.region_id.is_(None))
    elif region_id is not None:
        query = query.filter(models.City.region_id == region_id)
    return query.order_by(func.lower(models.City.name)).all()


def rename_place(db: Session, model, record_id: int, name: str):
    """Renames a country/region/city - 'not_found', 'taken' (another
    record with that name, ignoring case, under the same parent), or the
    updated record."""
    record = db.get(model, record_id)
    if record is None:
        return "not_found"
    parents = {}
    if model is models.Region:
        parents = {"country_id": record.country_id}
    elif model is models.City:
        parents = {"country_id": record.country_id, "region_id": record.region_id}
    clash = _find_by_name(db, model, name, **parents)
    if clash is not None and clash.id != record.id:
        return "taken"
    record.name = name.strip()
    db.commit()
    db.refresh(record)
    return record


def delete_place(db: Session, model, record_id: int) -> str:
    """'not_found', 'in_use' (anything still points at it), or 'deleted'."""
    record = db.get(model, record_id)
    if record is None:
        return "not_found"
    column = {models.Country: "country_id", models.Region: "region_id", models.City: "city_id"}[model]
    users = [models.Location]
    if model is models.Country:
        users += [models.Region, models.City]
    elif model is models.Region:
        users += [models.City]
    if any(db.query(m).filter(getattr(m, column) == record_id).count() for m in users):
        return "in_use"
    db.delete(record)
    db.commit()
    return "deleted"
