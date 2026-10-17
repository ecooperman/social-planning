import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import ai_extraction, crud, schemas
from ..deps import get_db

router = APIRouter(prefix="/api/instagram-import", tags=["instagram-import"])

_SHORTCODE = re.compile(r"/(p|reel)/([^/?#]+)")


def _canonical_permalink(url: str) -> str:
    """A collection grid links posts in a few shapes (with or without the
    username, /p/ vs /reel/, tracking params) - reduce each to one URL so
    re-importing a collection recognizes posts it has already seen."""
    match = _SHORTCODE.search(url)
    if not match:
        return url
    kind, code = match.groups()
    return f"https://www.instagram.com/{kind}/{code}/"


def _describe_location(location) -> str:
    """How the batch's location is described to Claude - its label plus the
    place hierarchy, e.g. "Salem, MA (Salem, Massachusetts, United States)"."""
    parts = [p.name for p in (location.city, location.region, location.country) if p is not None]
    return f"{location.name} ({', '.join(parts)})" if parts else location.name


def _extract(caption: str, filed_under):
    try:
        return ai_extraction.extract_places(caption, filed_under)
    except RuntimeError as err:
        # ANTHROPIC_API_KEY unset - fail the whole import loudly rather
        # than silently skipping every post one at a time.
        raise HTTPException(status_code=503, detail=str(err))


def _pair_places(plans, places):
    """Matches a re-read post's places back to the plans an earlier import
    made from it: same name (ignoring case) first, then - if exactly as
    many of each are left - the rest in order, since Claude may word a
    name slightly differently the second time. Anything still unpaired is
    left alone rather than guessed at."""
    remaining_plans = list(plans)
    remaining_places = []
    pairs = []
    for place in places:
        match = next((p for p in remaining_plans if p.name.strip().lower() == place.name.strip().lower()), None)
        if match is not None:
            pairs.append((match, place))
            remaining_plans.remove(match)
        else:
            remaining_places.append(place)
    if remaining_plans and len(remaining_plans) == len(remaining_places):
        pairs.extend(zip(remaining_plans, remaining_places))
        remaining_plans = []
    return pairs, remaining_plans


@router.post("", response_model=schemas.InstagramImportResult)
def import_from_instagram(request: schemas.InstagramImportRequest, db: Session = Depends(get_db)):
    """Classifies each post's caption with Claude and creates one Plan per
    real place it finds - a seed generator, not a finisher (see
    ai_extraction.py's docstring). Each plan's URL is its source post, so a
    bad extraction is easy to trace and fix or delete afterward. Each also
    keeps the caption and where Claude read the place to be (parsed_*),
    which can differ from the batch's location - see models.Plan.

    Posts that already have a plan (matched by permalink) are skipped
    before calling Claude, so a collection can be re-imported as it grows -
    unless recheck_existing is set, in which case they're re-read to
    refresh their plans' caption and parsed location, never to add plans.
    """
    location = None
    if request.location_id is not None:
        location = crud.get_location(db, request.location_id)
        if location is None:
            raise HTTPException(status_code=400, detail="Unknown location")
    filed_under = _describe_location(location) if location else None

    existing_urls = crud.get_plan_urls(db)
    posts_skipped = posts_already_imported = posts_rechecked = plans_updated = 0
    created_names = []

    for post in request.posts:
        permalink = _canonical_permalink(post.permalink)
        if permalink in existing_urls:
            posts_already_imported += 1
            if not request.recheck_existing:
                continue
            plans = crud.get_plans_by_url(db, permalink)
            pairs, unpaired = _pair_places(plans, _extract(post.caption, filed_under))
            for plan, place in pairs:
                crud.set_parsed_location(db, plan, post.caption, place.city, place.region, place.country)
            for plan in unpaired:
                plan.caption = post.caption
            db.commit()
            posts_rechecked += 1
            plans_updated += len(pairs)
            continue

        places = _extract(post.caption, filed_under)
        if not places:
            posts_skipped += 1
            continue

        for place in places:
            plan = crud.create_plan(
                db,
                schemas.PlanCreate(
                    name=place.name,
                    description=place.notes.strip() or None,
                    url=permalink,
                    location_id=request.location_id,
                ),
                imported=True,
            )
            crud.set_parsed_location(db, plan, post.caption, place.city, place.region, place.country)
            db.commit()
            created_names.append(place.name)
        existing_urls.add(permalink)

    return schemas.InstagramImportResult(
        posts_processed=len(request.posts),
        posts_skipped=posts_skipped,
        posts_already_imported=posts_already_imported,
        plans_created=len(created_names),
        created_names=created_names,
        posts_rechecked=posts_rechecked,
        plans_updated=plans_updated,
    )
