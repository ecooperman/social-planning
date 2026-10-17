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


@router.post("", response_model=schemas.InstagramImportResult)
def import_from_instagram(request: schemas.InstagramImportRequest, db: Session = Depends(get_db)):
    """Classifies each post's caption with Claude and creates one Plan per
    real place it finds - a seed generator, not a finisher (see
    ai_extraction.py's docstring). Each plan's URL is its source post, so a
    bad extraction is easy to trace and fix or delete afterward.

    Posts that already have a plan (matched by permalink) are skipped
    before calling Claude, so a collection can be re-imported as it grows.
    """
    if request.location_id is not None and crud.get_location(db, request.location_id) is None:
        raise HTTPException(status_code=400, detail="Unknown location")

    existing_urls = crud.get_plan_urls(db)
    posts_skipped = posts_already_imported = 0
    created_names = []

    for post in request.posts:
        permalink = _canonical_permalink(post.permalink)
        if permalink in existing_urls:
            posts_already_imported += 1
            continue
        try:
            places = ai_extraction.extract_places(post.caption)
        except RuntimeError as err:
            # ANTHROPIC_API_KEY unset - fail the whole import loudly rather
            # than silently skipping every post one at a time.
            raise HTTPException(status_code=503, detail=str(err))

        if not places:
            posts_skipped += 1
            continue

        for place in places:
            crud.create_plan(
                db,
                schemas.PlanCreate(
                    name=place.name,
                    description=place.notes.strip() or None,
                    url=permalink,
                    location_id=request.location_id,
                ),
            )
            created_names.append(place.name)
        existing_urls.add(permalink)

    return schemas.InstagramImportResult(
        posts_processed=len(request.posts),
        posts_skipped=posts_skipped,
        posts_already_imported=posts_already_imported,
        plans_created=len(created_names),
        created_names=created_names,
    )
