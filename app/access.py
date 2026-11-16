"""Who may use this app: its administrators, and nobody else.

The app has no accounts of its own; it used to rely wholly on Cloudflare Access in front of it. Now it signs
in through the shared front door (the dashboard), and shared_python.owner_gate wraps the whole app, so every
page, API route and file refuses anyone but an administrator.

The one exception is trip-planning's plan picker, which reads plans from this app on this machine with no
person signed in: only GET /api/locations, /api/plans and /api/plans/<id> with the shared service token.
The manifest and icons are public (browsers fetch them with no cookie, for installing the app)."""
import hmac
import re

from shared_python import owner_gate

from . import config

_TRIPS_READS = re.compile(r"^/api/(locations|plans|plans/\d+)$")
PUBLIC_PATHS = ("/manifest.json", "/icons/")


def trips_read(request) -> bool:
    if request.method != "GET" or not config.PLANS_SERVICE_TOKEN or not _TRIPS_READS.match(request.url.path):
        return False
    supplied = request.headers.get("x-service-token", "")
    return hmac.compare_digest(supplied.encode(), config.PLANS_SERVICE_TOKEN.encode())


def install(app) -> None:
    owner_gate.install(
        app,
        admin_emails=lambda: config.ADMIN_EMAILS,
        dev_user_email=config.DEV_USER_EMAIL,
        service_access=trips_read,
        public_paths=PUBLIC_PATHS,
    )
