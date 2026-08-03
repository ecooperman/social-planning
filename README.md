# Social Planning

A small local app for keeping a running list of potential date/activity
ideas - name, description, a source URL (e.g. an Instagram or Facebook
post), and a date the idea might happen on.

## Run it

```bash
cd social-planning
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
python -m app.main
```

Then open http://127.0.0.1:8020 (host/port are set in `app/config.py`).

The SQLite database (`ideas.db`) is not created by the app itself - `alembic
upgrade head` creates it. This only needs to be run once for a fresh
install; see below for how schema changes are handled from here on.

## API-first design

The backend (`app/`) is a plain JSON REST API (`/api/ideas`, `/docs` for the
interactive Swagger UI) with no knowledge of the frontend. The frontend
(`static/`) is a thin vanilla-JS client with no build step, talking to the
API over `fetch`. That separation means the backend can be tested and used
entirely on its own, and the frontend can later be swapped for something
richer without touching the API.

Endpoints:

- `GET /api/ideas` - list all ideas
- `POST /api/ideas` - create an idea (`name` is the only required field)
- `GET /api/ideas/{id}` - fetch one idea
- `PATCH /api/ideas/{id}` - update any subset of fields, including
  `event_date` (send `null` to clear it)
- `DELETE /api/ideas/{id}` - delete an idea
- `POST /api/ideas/{id}/scrape` - (re-)run the scraper for the idea's URL and
  persist the result onto the idea

## Schema changes (Alembic)

Schema is owned by migrations under `migrations/versions/`, not by wiping
`ideas.db`. To change the schema:

```bash
# 1. Edit app/models.py as usual
# 2. Generate a migration from the diff
alembic revision --autogenerate -m "short description"
# 3. Look over the generated file in migrations/versions/ - autogenerate
#    is good but not infallible (e.g. it won't detect a plain column rename
#    on its own)
# 4. Apply it
alembic upgrade head
```

This preserves existing data. Useful commands: `alembic current` (what
revision the db is at), `alembic check` (does the db match `models.py`
right now), `alembic downgrade -1` (undo the last migration).

SQLite can't `ALTER TABLE` to add a constraint directly, so
`migrations/env.py` has `render_as_batch=True` set, which makes autogenerate
wrap those changes in `op.batch_alter_table(...)` (SQLite rebuilds the table
under the hood). If autogenerate produces a `batch_op.create_foreign_key(None,
...)` / `drop_constraint(None, ...)` call, give it an explicit name in both
`upgrade()` and `downgrade()` - SQLite's batch mode needs a name to
reference, and will fail with `ValueError: Constraint must have a name`
otherwise.

## Upgrading to Postgres later

Everything goes through SQLAlchemy + Alembic, so moving off SQLite is mostly
a matter of swapping `DATABASE_URL` in `app/database.py` (and
`sqlalchemy.url` in `alembic.ini`) for a Postgres connection string,
installing a driver (`psycopg`), and running `alembic upgrade head` against
the new database - no application code depends on SQLite specifics.

## Scraping framework

`app/scraping/` holds the strategy framework for pulling a title, description,
and image out of a URL:

- `base.py` - `ScraperStrategy` interface (`matches(url)` / `scrape(url)`)
  and the `ScrapedContent` result shape
- `og_tags.py` - shared helper that fetches a page and reads its Open Graph
  meta tags (`og:title`, `og:description`, `og:image`) - the common ground
  between Instagram and Facebook (and most link-preview-friendly sites)
- `instagram.py`, `facebook.py` - the two concrete strategies, matching on
  hostname and delegating to `og_tags`
- `registry.py` - picks the first strategy whose `matches()` returns true
  for a given URL
- `service.py` - orchestrates a scrape and persists the outcome (success,
  failed, or unsupported) onto the idea via `crud.save_scrape_result`

Adding support for another site later is just a new `ScraperStrategy`
subclass registered in `registry.py`.

Note: Instagram and Facebook both increasingly gate content behind a login
wall for logged-out/bot requests, so a scrape can legitimately come back
`failed` ("No Open Graph metadata found...") for some posts even though the
strategy matched. That's surfaced back to the UI rather than treated as a
crash - scraping is a nice-to-have on top of the manually-entered fields,
never a requirement.

## Notes

- Only `name` is required on an idea - everything else (description, URL,
  date) is optional and can be filled in later.
- The date field is directly editable from the list view (a native date
  input on each card) - no separate edit mode needed just to change when an
  idea might happen.
- Editing name/description/URL is done via the idea's name, which opens an
  inline edit form.
- The "Fetch preview" button only appears when an idea has a URL, and calls
  `POST /api/ideas/{id}/scrape`. It can be re-run any time (e.g. after a
  transient failure) via "Re-fetch preview".
