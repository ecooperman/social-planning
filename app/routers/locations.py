from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..deps import get_db

router = APIRouter(prefix="/api/locations", tags=["locations"])


def _clean_name(db: Session, name: str, exclude_id: int = None) -> str:
    name = name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Location name is required")
    if crud.location_name_taken(db, name, exclude_id):
        raise HTTPException(status_code=409, detail=f'A location named "{name}" already exists')
    return name


@router.get("", response_model=List[schemas.Location])
def list_locations(db: Session = Depends(get_db)):
    return crud.get_locations(db)


@router.post("", response_model=schemas.Location)
def create_location(location: schemas.LocationCreate, db: Session = Depends(get_db)):
    location.name = _clean_name(db, location.name)
    return crud.create_location(db, location)


@router.patch("/{location_id}", response_model=schemas.Location)
def update_location(location_id: int, updates: schemas.LocationUpdate, db: Session = Depends(get_db)):
    if updates.name is not None:
        updates.name = _clean_name(db, updates.name, exclude_id=location_id)
    location = crud.update_location(db, location_id, updates)
    if location is None:
        raise HTTPException(status_code=404, detail="Location not found")
    return location


@router.delete("/{location_id}")
def delete_location(location_id: int, db: Session = Depends(get_db)):
    result = crud.delete_location(db, location_id)
    if result == "not_found":
        raise HTTPException(status_code=404, detail="Location not found")
    if result == "in_use":
        raise HTTPException(status_code=409, detail="Location is still set on one or more plans")
    return {"ok": True}
