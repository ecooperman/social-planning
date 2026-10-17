from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..deps import get_db
from ..scraping.service import scrape_plan

router = APIRouter(prefix="/api/plans", tags=["plans"])


def _check_location(db: Session, location_id):
    if location_id is not None and crud.get_location(db, location_id) is None:
        raise HTTPException(status_code=400, detail="Unknown location")


@router.get("", response_model=List[schemas.Plan])
def list_plans(location_id: Optional[int] = None, db: Session = Depends(get_db)):
    return crud.get_plans(db, location_id=location_id)


@router.post("", response_model=schemas.Plan)
def create_plan(plan: schemas.PlanCreate, db: Session = Depends(get_db)):
    _check_location(db, plan.location_id)
    return crud.create_plan(db, plan)


@router.get("/{plan_id}", response_model=schemas.Plan)
def get_plan(plan_id: int, db: Session = Depends(get_db)):
    plan = crud.get_plan(db, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan


@router.patch("/{plan_id}", response_model=schemas.Plan)
def update_plan(plan_id: int, updates: schemas.PlanUpdate, db: Session = Depends(get_db)):
    _check_location(db, updates.location_id)
    plan = crud.update_plan(db, plan_id, updates)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan


@router.delete("/{plan_id}")
def delete_plan(plan_id: int, db: Session = Depends(get_db)):
    ok = crud.delete_plan(db, plan_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Plan not found")
    return {"ok": True}


@router.post("/{plan_id}/scrape", response_model=schemas.Plan)
def trigger_scrape(plan_id: int, db: Session = Depends(get_db)):
    plan = crud.get_plan(db, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    if not plan.url:
        raise HTTPException(status_code=400, detail="Plan has no URL to scrape")
    return scrape_plan(db, plan_id, plan.url)
