"""Who may use this app, and whose data they see.

Several people can have an account, each with completely private data. The app has no accounts of its own to
check against until someone is let in (default-deny): an administrator adds a person on the Users page, or, for an
administrator, the account is made on their first sign-in (taking over the data that existed before accounts).

shared_python.accounts_gate wraps the WHOLE app: every page, API route and file refuses anyone without an account,
and runs each request inside that person's scope, so every database read and write is filtered to them below the
routes' own code (shared_python.owned). Only an administrator may use what costs money or acts as the administrator:
the Google place lookup, the Instagram import and sending plans to trip-planning (see routers/).

The one exception is trip-planning's plan picker, which reads plans from this app on this machine with no person
signed in: only GET /api/locations, /api/plans and /api/plans/<id> with the shared service token, acting as the
administrator (so it can only ever see the administrator's own plans).
The manifest and icons are public (browsers fetch them with no cookie, for installing the app)."""
import hmac
import re
from typing import Optional, Union

from shared_python import accounts_gate, usage
from shared_python.accounts_gate import Account

from . import config, crud, models
from .database import SessionLocal

_TRIPS_READS = re.compile(r"^/api/(locations|plans|plans/\d+)$")
PUBLIC_PATHS = ("/manifest.json", "/icons/")
seen = usage.LastSeen(SessionLocal)  # when each person was last here, for the dashboard's stats pages


def account_for(email: str) -> Union[Account, str]:
    """This person's account in the app: administrators always have one (made on first sign-in), anyone else only
    if an administrator let them in and has not since removed them."""
    is_admin = email in config.ADMIN_EMAILS
    with SessionLocal() as db:
        user = crud.get_user_by_email(db, email)
        if user is None:
            if not is_admin:
                return "none"
            user = crud.adopt_or_create_admin(db, email)
        if user.status != models.USER_ACTIVE and not is_admin:
            return "removed"
        return Account(id=user.id, email=user.email, is_admin=is_admin)


def trips_read(request) -> Optional[Account]:
    """trip-planning's three read-only calls, acting as the first administrator (and nobody else)."""
    if request.method != "GET" or not config.PLANS_SERVICE_TOKEN or not _TRIPS_READS.match(request.url.path):
        return None
    supplied = request.headers.get("x-service-token", "")
    if not hmac.compare_digest(supplied.encode(), config.PLANS_SERVICE_TOKEN.encode()):
        return None
    admins = sorted(config.ADMIN_EMAILS)
    found = account_for(admins[0]) if admins else None
    return found if isinstance(found, Account) else None


def install(app) -> None:
    accounts_gate.install(
        app,
        account_for=account_for,
        dev_user_email=config.DEV_USER_EMAIL,
        service_account=trips_read,
        public_paths=PUBLIC_PATHS,
        seen=seen,
    )
