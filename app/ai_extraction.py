"""Turns a saved Instagram post's caption into zero or more candidate
plans, via the Claude API. Used by the "import a saved collection" flow
(see routers/instagram_import.py and the web-capture Chrome extension's
collection-grid extractor). Moved here from trip-planning, which now pulls
plans in as activities instead of importing Instagram posts itself.

One caption can describe several distinct real places (a numbered
neighborhood guide, a "top 5 spots" post, ...) - see extract_places for how
that's handled. This is deliberately a seed generator, not a finisher:
results are meant to be reviewed/edited on the plans page after import, so
a wrong or approximate name is an acceptable, expected outcome, not a bug
to chase out here.
"""
from typing import List

import anthropic
from pydantic import BaseModel

from .config import ANTHROPIC_API_KEY

MODEL = "claude-opus-5-5"

SYSTEM_PROMPT = """You read Instagram captions and decide whether they \
describe real-world places or activities a traveler could actually visit \
(a restaurant, cafe, shop, museum, hike, neighborhood, landmark, etc.).

Many captions are NOT about a visitable place at all - a meme, a personal \
photo, a product ad, a life update, a repost with no location. For those, \
return an empty list.

Some captions describe exactly one place. Others are a guide or roundup \
that names several distinct places - a numbered list, a "top N spots" \
post, or a neighborhood guide. In that case, extract EACH distinct place \
as its own entry, not one combined entry.

Places are sometimes named in plain prose ("Le Comptoir on Rue X"), and \
sometimes only via an Instagram @handle for that business's own account \
(e.g. "@wonderpens"). For an @handle, turn it into a plausible readable \
business name (e.g. "@wonderpens" -> "Wonder Pens") using whatever you \
know of the real place if you recognize it, or a reasonable cleaned-up \
guess otherwise - note in that entry's notes that the name is inferred \
from the handle, not stated outright, so it's easy to spot and fix.

For each place, write 1-3 sentences of notes capturing whatever the \
caption actually says about it (why it's recommended, what to get/do \
there, hours or tips mentioned) - don't invent details the caption \
doesn't contain."""


class ExtractedPlace(BaseModel):
    name: str
    notes: str


class CaptionExtraction(BaseModel):
    # Field name kept from the trips version of this prompt/schema - the
    # prompt never names it, so renaming it buys nothing.
    activities: List[ExtractedPlace]


def _client() -> anthropic.Anthropic:
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured")
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def extract_places(caption: str) -> List[ExtractedPlace]:
    """Returns the candidate places found in one caption - an empty list if
    the caption doesn't describe a visitable place at all, or if the
    request was declined (treated the same as "not a place": the post is
    counted as skipped rather than failing the whole import)."""
    if not caption or not caption.strip():
        return []

    response = _client().beta.messages.parse(
        model=MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": caption}],
        output_format=CaptionExtraction,
        # Short, simple extraction - low effort is plenty and keeps a
        # many-post import quick and cheap.
        output_config={"effort": "low"},
        # On a safety-classifier decline, re-run on Anthropic's recommended
        # fallback model inside the same call instead of losing the post.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    if response.stop_reason == "refusal" or response.parsed_output is None:
        return []
    return response.parsed_output.activities
