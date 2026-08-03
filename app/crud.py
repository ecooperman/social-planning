from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from . import models, schemas


def get_ideas(db: Session):
    return db.query(models.Idea).order_by(
        models.Idea.event_date.is_(None), models.Idea.event_date, models.Idea.created_at.desc()
    ).all()


def get_idea(db: Session, idea_id: int):
    return db.query(models.Idea).filter(models.Idea.id == idea_id).first()


def create_idea(db: Session, idea: schemas.IdeaCreate):
    db_idea = models.Idea(**idea.model_dump())
    db.add(db_idea)
    db.commit()
    db.refresh(db_idea)
    return db_idea


def update_idea(db: Session, idea_id: int, updates: schemas.IdeaUpdate):
    db_idea = get_idea(db, idea_id)
    if db_idea is None:
        return None
    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(db_idea, field, value)
    db.commit()
    db.refresh(db_idea)
    return db_idea


def delete_idea(db: Session, idea_id: int) -> bool:
    db_idea = get_idea(db, idea_id)
    if db_idea is None:
        return False
    db.delete(db_idea)
    db.commit()
    return True


def save_scrape_result(
    db: Session,
    idea_id: int,
    status: models.ScrapeStatus,
    title: Optional[str] = None,
    description: Optional[str] = None,
    image_url: Optional[str] = None,
    error: Optional[str] = None,
):
    db_idea = get_idea(db, idea_id)
    if db_idea is None:
        return None
    db_idea.scrape_status = status
    db_idea.scraped_title = title
    db_idea.scraped_description = description
    db_idea.scraped_image_url = image_url
    db_idea.scrape_error = error
    db_idea.scraped_at = datetime.utcnow()
    db.commit()
    db.refresh(db_idea)
    return db_idea
