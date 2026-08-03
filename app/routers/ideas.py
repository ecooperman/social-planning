from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..deps import get_db
from ..scraping.service import scrape_idea

router = APIRouter(prefix="/api/ideas", tags=["ideas"])


@router.get("", response_model=List[schemas.Idea])
def list_ideas(db: Session = Depends(get_db)):
    return crud.get_ideas(db)


@router.post("", response_model=schemas.Idea)
def create_idea(idea: schemas.IdeaCreate, db: Session = Depends(get_db)):
    return crud.create_idea(db, idea)


@router.get("/{idea_id}", response_model=schemas.Idea)
def get_idea(idea_id: int, db: Session = Depends(get_db)):
    idea = crud.get_idea(db, idea_id)
    if idea is None:
        raise HTTPException(status_code=404, detail="Idea not found")
    return idea


@router.patch("/{idea_id}", response_model=schemas.Idea)
def update_idea(idea_id: int, updates: schemas.IdeaUpdate, db: Session = Depends(get_db)):
    idea = crud.update_idea(db, idea_id, updates)
    if idea is None:
        raise HTTPException(status_code=404, detail="Idea not found")
    return idea


@router.delete("/{idea_id}")
def delete_idea(idea_id: int, db: Session = Depends(get_db)):
    ok = crud.delete_idea(db, idea_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Idea not found")
    return {"ok": True}


@router.post("/{idea_id}/scrape", response_model=schemas.Idea)
def trigger_scrape(idea_id: int, db: Session = Depends(get_db)):
    idea = crud.get_idea(db, idea_id)
    if idea is None:
        raise HTTPException(status_code=404, detail="Idea not found")
    if not idea.url:
        raise HTTPException(status_code=400, detail="Idea has no URL to scrape")
    return scrape_idea(db, idea_id, idea.url)
