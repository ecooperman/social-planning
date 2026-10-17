from datetime import datetime
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from . import models, schemas


def get_locations(db: Session):
    return db.query(models.Location).order_by(func.lower(models.Location.name)).all()


def get_location(db: Session, location_id: int):
    return db.query(models.Location).filter(models.Location.id == location_id).first()


def location_name_taken(db: Session, name: str, exclude_id: Optional[int] = None) -> bool:
    """Case-insensitive, so "tokyo" can't sit alongside "Tokyo" - the whole
    point of a picked-from-a-list location is one spelling per place."""
    query = db.query(models.Location).filter(func.lower(models.Location.name) == name.lower())
    if exclude_id is not None:
        query = query.filter(models.Location.id != exclude_id)
    return query.first() is not None


def create_location(db: Session, location: schemas.LocationCreate):
    db_location = models.Location(**location.model_dump())
    db.add(db_location)
    db.commit()
    db.refresh(db_location)
    return db_location


def update_location(db: Session, location_id: int, updates: schemas.LocationUpdate):
    db_location = get_location(db, location_id)
    if db_location is None:
        return None
    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(db_location, field, value)
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
