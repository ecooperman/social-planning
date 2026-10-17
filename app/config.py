import os

HOST = "127.0.0.1"
PORT = 8020

# "local" (default, for `uvicorn app.main:app --reload` on a dev machine) or
# "production" (set once, droplet-wide, via systemd's DefaultEnvironment -
# see DEPLOYMENT.md - so every app inherits it with no per-service config).
# Drives which shared-assets host the app's templates point at, so
# switching between local iteration and the real deploy never means
# hand-editing a URL and remembering to revert it.
ENV = os.environ.get("APP_ENV", "local")
SHARED_ASSETS_BASE = "https://static.evancooperman.com" if ENV == "production" else "http://127.0.0.1:8070"

# trip-planning - a plan can be sent there as an activity (optionally on a
# trip), and trips keeps the resulting Activity.plan_id link (see
# routers/trips_link.py). API calls go server-to-server on 127.0.0.1, same
# as finances -> trips, which sidesteps Cloudflare Access entirely.
# TRIPS_PUBLIC_URL is only for links a browser follows to a trip.
TRIPS_API_BASE = os.environ.get("TRIPS_API_BASE", "http://127.0.0.1:8060")
TRIPS_PUBLIC_URL = "https://trips.evancooperman.com" if ENV == "production" else "http://127.0.0.1:8060"

# Used by app/ai_extraction.py to turn Instagram captions into candidate
# plans. Never committed - exported in your shell for local dev; on the
# droplet it comes from the shared secrets file every app reads
# (/etc/personal-apps/shared.env, see DEPLOYMENT.md). The Instagram import
# fails with a clear 503 (not a silent no-op) if this is unset.
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
