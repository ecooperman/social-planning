from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, places, schemas
from ..deps import get_db

router = APIRouter(prefix="/api/locations", tags=["locations"])


def _clean_name(db: Session, name: str, exclude_id: int = None) -> str:
    name = name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Location name is required")
    if crud.location_name_taken(db, name, exclude_id):
        raise HTTPException(status_code=409, detail=f'A location named "{name}" already exists')
    return name


def _check_place(db: Session, place_id, exclude_id: int = None):
    if not place_id:
        return
    existing = crud.get_location_by_place_id(db, place_id)
    if existing is not None and existing.id != exclude_id:
        raise HTTPException(status_code=409, detail=f'That place is already added as "{existing.name}"')


@router.get("/lookup/available")
def lookup_available():
    """Whether the Google place lookup is configured - settings.html hides
    the search box (manual entry only) when it isn't."""
    return {"available": places.available()}


@router.get("/lookup", response_model=List[schemas.PlaceSuggestion])
def lookup(q: str):
    if not q.strip():
        return []
    try:
        return places.autocomplete(q.strip())
    except places.PlacesError as err:
        raise HTTPException(status_code=502, detail=str(err))


@router.get("/lookup/{place_id}", response_model=schemas.PlaceDetails)
def lookup_details(place_id: str, db: Session = Depends(get_db)):
    try:
        details = places.details(place_id)
    except places.PlacesError as err:
        raise HTTPException(status_code=502, detail=str(err))
    # Point the form at records that already exist, so a lookup reuses
    # "United States" rather than offering to create it again.
    country = crud.find_country(db, details.country) if details.country else None
    region = crud.find_region(db, country.id, details.region) if country and details.region else None
    city = (
        crud.find_city(db, country.id, region.id if region else None, details.city)
        if country and details.city
        else None
    )
    details.country_id = country.id if country else None
    details.region_id = region.id if region else None
    details.city_id = city.id if city else None
    return details


@router.get("", response_model=List[schemas.Location])
def list_locations(db: Session = Depends(get_db)):
    return crud.get_locations(db)


@router.post("", response_model=schemas.Location)
def create_location(location: schemas.LocationCreate, db: Session = Depends(get_db)):
    location.name = _clean_name(db, location.name)
    _check_place(db, location.place_id)
    try:
        return crud.create_location(db, location)
    except crud.PlaceError as err:
        raise HTTPException(status_code=400, detail=str(err))


@router.patch("/{location_id}", response_model=schemas.Location)
def update_location(location_id: int, updates: schemas.LocationUpdate, db: Session = Depends(get_db)):
    if updates.name is not None:
        updates.name = _clean_name(db, updates.name, exclude_id=location_id)
    _check_place(db, updates.place_id, exclude_id=location_id)
    try:
        location = crud.update_location(db, location_id, updates)
    except crud.PlaceError as err:
        raise HTTPException(status_code=400, detail=str(err))
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
