"""FastAPI application for the MTG Deck Builder."""
import os
import traceback
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import DB_PATH, STATIC_DIR, TEMPLATES_DIR, TURSO_DATABASE_URL
from app.database import init_db
from app.routers import cards, decks, export, pages


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the database on startup."""
    # Banner: make the DB mode obvious in Vercel function logs so a missing
    # Turso env var doesn't suffer in silence (decks would vanish because each
    # warm instance would get its own ephemeral /tmp/magic.db).
    if TURSO_DATABASE_URL:
        # Only print the scheme+host so we don't leak the auth token if the
        # URL ever had one embedded (it shouldn't — token is separate).
        safe = TURSO_DATABASE_URL.split("@")[-1] if "@" in TURSO_DATABASE_URL else TURSO_DATABASE_URL
        print(f"[startup] DB mode: Turso (remote libSQL) -> {safe}", flush=True)
    else:
        print(
            f"[startup] DB mode: LOCAL FILE ({DB_PATH}) — "
            "TURSO_DATABASE_URL is NOT SET; on Vercel this means each function "
            "instance has its own ephemeral DB and decks will not persist. "
            "Set TURSO_DATABASE_URL and TURSO_AUTH_TOKEN in Project Settings.",
            flush=True,
        )
    try:
        await init_db()
    except Exception as e:
        # Vercel's platform collapses lifespan exceptions into a generic
        # "Application startup failed" message on the 500 page. Print the
        # real traceback so it surfaces in the Vercel function logs for
        # diagnosis, then re-raise so the function still fails loudly.
        print(f"[startup] init_db failed: {e!r}", flush=True)
        traceback.print_exc()
        raise
    yield


app = FastAPI(title="MTG Deck Builder", lifespan=lifespan)

# Serve /static from the filesystem in local/Docker dev. On Vercel, the VERCEL
# env var is set and vercel.json rewrites fall through to the CDN-served
# public/static/ directory, so we skip the mount here to avoid double-handling
# and function invocations for asset requests.
if not os.environ.get("VERCEL"):
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Jinja2 templates
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Register routers
app.include_router(pages.router)
app.include_router(cards.router, prefix="/api")
app.include_router(decks.router, prefix="/api")
app.include_router(export.router)


@app.exception_handler(404)
async def not_found_handler(request: Request, exc: Exception):
    """Render a friendly 404 page for HTML requests."""
    if "text/html" in request.headers.get("accept", ""):
        return templates.TemplateResponse(
            request,
            "error.html",
            {"status_code": 404, "message": "Page not found"},
            status_code=404,
        )
    return HTMLResponse(status_code=404, content="Not found")
