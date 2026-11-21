from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from shared_python import accounts_gate, oidc_login

from . import access, places, schemas
from .config import SHARED_ASSETS_BASE
from .routers import geo, instagram_import, locations, plans, stats, trips_link, users

# Schema is owned by Alembic migrations (see migrations/) - run
# `alembic upgrade head` before starting the app rather than relying on
# create_all, so schema changes never silently bypass migrations.

app = FastAPI(title="Social Planning")
access.install(app)  # only people with an account get in, each inside their own private data (app/access.py)
templates = Jinja2Templates(directory="templates")


@app.get("/api/me", response_model=schemas.Me)
def get_me(request: Request, account=Depends(accounts_gate.current_account)):
    """Who is signed in, for the page header and for hiding what only an administrator may use."""
    return schemas.Me(
        id=account.id,
        email=account.email,
        is_admin=account.is_admin,
        can_use={"places": account.is_admin and places.available(), "instagram": account.is_admin, "trips": account.is_admin},
        logout_url=oidc_login.logout_url(request),
    )


# shared_assets_base baked in server-side (no client-side fetch, no flash
# of unstyled content) - see config.py's SHARED_ASSETS_BASE. Registered
# before the StaticFiles mount below so this takes priority over it.
def _render(name: str):
    def route(request: Request):
        return templates.TemplateResponse(request, name, {"shared_assets_base": SHARED_ASSETS_BASE})

    return route


app.get("/", response_class=HTMLResponse)(_render("index.html"))
app.get("/settings.html", response_class=HTMLResponse)(_render("settings.html"))
app.get("/users.html", response_class=HTMLResponse)(_render("users.html"))


app.include_router(plans.router)
app.include_router(locations.router)
app.include_router(geo.router)
app.include_router(trips_link.router)
app.include_router(instagram_import.router)
app.include_router(users.router)
app.include_router(stats.router)

app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn

    from .config import HOST, PORT

    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=True)
