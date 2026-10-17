"""The country -> region -> city lists behind locations (see
models.Country). New entries are only ever created by saving a location
(crud.resolve_place); these endpoints list them for the location form's
dropdowns and let the Settings page fix a spelling or remove an unused one.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..deps import get_db

router = APIRouter(prefix="/api", tags=["geo"])

LABELS = {models.Country: "country", models.Region: "state/region", models.City: "city"}


def _rename(db: Session, model, record_id: int, body: schemas.Rename):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    result = crud.rename_place(db, model, record_id, name)
    if result == "not_found":
        raise HTTPException(status_code=404, detail=f"{LABELS[model].capitalize()} not found")
    if result == "taken":
        raise HTTPException(status_code=409, detail=f'There is already a {LABELS[model]} named "{name}" there')
    return result


def _delete(db: Session, model, record_id: int):
    result = crud.delete_place(db, model, record_id)
    if result == "not_found":
        raise HTTPException(status_code=404, detail=f"{LABELS[model].capitalize()} not found")
    if result == "in_use":
        raise HTTPException(status_code=409, detail=f"That {LABELS[model]} is still used by a location or a place inside it")
    return {"ok": True}


@router.get("/countries", response_model=List[schemas.Country])
def list_countries(db: Session = Depends(get_db)):
    return crud.get_countries(db)


@router.patch("/countries/{country_id}", response_model=schemas.Country)
def rename_country(country_id: int, body: schemas.Rename, db: Session = Depends(get_db)):
    return _rename(db, models.Country, country_id, body)


@router.delete("/countries/{country_id}")
def delete_country(country_id: int, db: Session = Depends(get_db)):
    return _delete(db, models.Country, country_id)


@router.get("/regions", response_model=List[schemas.Region])
def list_regions(country_id: Optional[int] = None, db: Session = Depends(get_db)):
    return crud.get_regions(db, country_id)


@router.patch("/regions/{region_id}", response_model=schemas.Region)
def rename_region(region_id: int, body: schemas.Rename, db: Session = Depends(get_db)):
    return _rename(db, models.Region, region_id, body)


@router.delete("/regions/{region_id}")
def delete_region(region_id: int, db: Session = Depends(get_db)):
    return _delete(db, models.Region, region_id)


@router.get("/cities", response_model=List[schemas.City])
def list_cities(
    country_id: Optional[int] = None,
    region_id: Optional[int] = None,
    no_region: bool = False,
    db: Session = Depends(get_db),
):
    """no_region=true lists a country's cities that sit directly under it
    (a country with no states) rather than inside a region."""
    return crud.get_cities(db, country_id, region_id, no_region)


@router.patch("/cities/{city_id}", response_model=schemas.City)
def rename_city(city_id: int, body: schemas.Rename, db: Session = Depends(get_db)):
    return _rename(db, models.City, city_id, body)


@router.delete("/cities/{city_id}")
def delete_city(city_id: int, db: Session = Depends(get_db)):
    return _delete(db, models.City, city_id)
