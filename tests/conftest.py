"""The suite runs against a throwaway SQLite file built by the real migrations, so it
exercises the schema the app ships with and can never touch the real ideas.db:
DATABASE_URL is set (and the schema built) before app.main is imported, because
app/database.py reads it when it loads. Every table is emptied before each test.

Nothing in the suite may reach the network: requests (Google, trip-planning, Instagram)
and the Claude client are replaced by an error unless a test supplies its own fake."""
import os
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_db_file.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_db_file.name}"
# The app reads templates/ and static/ relative to the working directory.
os.chdir(ROOT)

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402

_cfg = Config(str(ROOT / "alembic.ini"))
_cfg.set_main_option("script_location", str(ROOT / "migrations"))
command.upgrade(_cfg, "head")

import requests  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from shared_python import settings as shared_settings  # noqa: E402

from shared_python import owned  # noqa: E402

from app import ai_extraction, config, crud, models, places, schemas  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.routers import trips_link  # noqa: E402


def pytest_sessionfinish(session, exitstatus):
    os.unlink(_db_file.name)


@pytest.fixture(autouse=True)
def clean_db():
    """Empty every table, then give the dev user (an administrator locally) an account and run the test inside THEIR
    scope: the app now keeps every person's data private, so even a test's own database calls belong to someone.
    Use `make_user`, `as_user` and `client_as` (below) to bring in a second person."""
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
    with owned.unscoped(), SessionLocal() as session:
        dev = models.User(email=config.DEV_USER_EMAIL)
        session.add(dev)
        session.commit()
        dev_id = dev.id
    with owned.scope(dev_id):
        yield


@pytest.fixture()
def make_user():
    """make_user("bob@example.com") -> the new person's id (an account: they have been let in)."""

    def make(email, status=models.USER_ACTIVE):
        with owned.unscoped(), SessionLocal() as session:
            user = models.User(email=email, status=status)
            session.add(user)
            session.commit()
            return user.id

    return make


@pytest.fixture()
def as_user():
    """`with as_user(person_id) as db:` a fresh database session working as that person (never mixes with another)."""
    from contextlib import contextmanager

    @contextmanager
    def work(person_id):
        with owned.scope(person_id), SessionLocal() as session:
            yield session

    return work


@pytest.fixture()
def client_as():
    """client_as("bob@example.com") -> a client making every request as that person (locally the header says who)."""

    def make(email):
        return TestClient(app, headers={"Cf-Access-Authenticated-User-Email": email})

    return make


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError(f"a test tried to reach the network: {args[:2]}")

    monkeypatch.setattr(requests, "request", refuse)
    monkeypatch.setattr(requests, "get", refuse)
    monkeypatch.setattr(ai_extraction, "_client", refuse)
    # Keys must not leak in from the developer's shell either way.
    monkeypatch.setattr(config, "GOOGLE_MAPS_API_KEY", None)
    monkeypatch.setattr(places, "GOOGLE_MAPS_API_KEY", None)
    monkeypatch.setattr(trips_link, "TRIPS_SERVICE_TOKEN", None)
    # Whatever sign-in settings the developer's shell has, tests start local, with the dev user as the administrator.
    for name in (
        "CF_TEAM_DOMAIN", "CF_ACCESS_AUD", "OIDC_ISSUER", "OIDC_JWKS_URL", "OIDC_AUDIENCE", "OIDC_COOKIE", "OIDC_CLIENT_ID",
        "OIDC_CLIENT_SECRET", "OIDC_COOKIE_DOMAIN", "OIDC_RETURN_HOSTS", "OIDC_LOGIN_URL", "OIDC_LOGOUT_RETURN_PATH",
    ):
        monkeypatch.setattr(shared_settings, name, None)
    monkeypatch.setattr(shared_settings, "ENV", "local")
    monkeypatch.setattr(config, "PLANS_SERVICE_TOKEN", None)


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture()
def db():
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture()
def make_location(db):
    """make_location("Montreal", new_country="Canada", new_region="Quebec", new_city="Montreal")."""

    def make(name, **place):
        return crud.create_location(db, schemas.LocationCreate(name=name, **place))

    return make


@pytest.fixture()
def make_plan(db):
    def make(name="A plan", imported=False, **fields):
        return crud.create_plan(db, schemas.PlanCreate(name=name, **fields), imported=imported)

    return make


@pytest.fixture()
def Plan():
    return models.Plan
