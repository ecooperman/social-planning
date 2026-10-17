"""The plans side of the social-planning <-> trip-planning link - thin
proxies to trip-planning's /api/plan-links, which owns both the link
(Activity.plan_id) and the logic for turning a plan into an activity. See
trip-planning's routers/plan_links.py for the full picture.

Proxied rather than called from the browser so the request goes
server-to-server on 127.0.0.1 (no CORS, no Cloudflare Access hop).
"""
from typing import Optional

import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import TRIPS_API_BASE, TRIPS_PUBLIC_URL

router = APIRouter(prefix="/api/trips-link", tags=["trips-link"])


def _trips_request(method: str, path: str, **kwargs):
    try:
        resp = requests.request(method, f"{TRIPS_API_BASE}{path}", timeout=10, **kwargs)
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Couldn't reach the trips app: {exc}")
    if not resp.ok:
        try:
            detail = resp.json().get("detail")
        except ValueError:
            detail = None
        # Pass a 4xx through (e.g. "Trip not found") - it's the caller's
        # mistake, not the trips app being down.
        status = resp.status_code if 400 <= resp.status_code < 500 else 502
        raise HTTPException(status_code=status, detail=detail or f"Trips app returned {resp.status_code}")
    return resp.json()


@router.get("/trips")
def list_trips():
    """Non-archived trips, for the "Send to trips" picker."""
    trips = _trips_request("GET", "/api/trips")
    return [{"id": t["id"], "location": t["location"]} for t in trips if not t.get("archived")]


@router.get("/links")
def list_links():
    """Every activity created from a plan - fetched once per page load and
    matched up client-side, rather than one call per plan card."""
    return {"trips_url": TRIPS_PUBLIC_URL, "links": _trips_request("GET", "/api/plan-links")}


class SendRequest(BaseModel):
    plan_id: int
    # Optional - omit to create an activity that isn't on any trip yet.
    trip_id: Optional[int] = None


@router.post("/send")
def send_to_trips(request: SendRequest):
    return _trips_request(
        "POST",
        "/api/plan-links/import",
        json={"plan_ids": [request.plan_id], "trip_id": request.trip_id},
    )
