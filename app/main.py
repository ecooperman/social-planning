from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import SHARED_ASSETS_BASE
from .routers import ideas

# Schema is owned by Alembic migrations (see migrations/) - run
# `alembic upgrade head` before starting the app rather than relying on
# create_all, so schema changes never silently bypass migrations.

app = FastAPI(title="Social Planning")
templates = Jinja2Templates(directory="templates")


# shared_assets_base baked in server-side (no client-side fetch, no flash
# of unstyled content) - see config.py's SHARED_ASSETS_BASE. Registered
# before the StaticFiles mount below so this takes priority over it.
@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {"shared_assets_base": SHARED_ASSETS_BASE})


app.include_router(ideas.router)

app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn

    from .config import HOST, PORT

    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=True)
