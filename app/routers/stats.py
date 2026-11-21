"""What the dashboard's stats pages ask this app: for each account, when they were last here and how much they have in the app, as
numbers and dates only (never a plan's name, link or notes). Administrators only. The counts run inside `owned.unscoped()` because
every table here is private to its owner: this is the one place everyone's rows are counted together."""
from fastapi import APIRouter, Depends
from shared_python import accounts_gate, owned, usage

from .. import models
from ..database import SessionLocal

router = APIRouter(prefix="/api/admin/stats", tags=["stats"], dependencies=[Depends(accounts_gate.require_admin)])


@router.get("")
def stats():
    with owned.unscoped(), SessionLocal() as db:
        return usage.build(db, models.User, {
            "plans": usage.per_user(db, models.Plan.owner_id, models.Plan.created_at),
            "plans imported in bulk": usage.per_user(db, models.Plan.owner_id, None, models.Plan.imported.is_(True)),
            "locations": usage.per_user(db, models.Location.owner_id, models.Location.created_at),
        })
