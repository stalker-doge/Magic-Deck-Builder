"""Application configuration."""
import os
from pathlib import Path

# Project root (parent of the app/ directory)
BASE_DIR = Path(__file__).resolve().parent.parent

# SQLite database file. Overridable via env var so the Docker container can
# point at a named-volume path (e.g. /data/magic.db) without code changes.
# When TURSO_DATABASE_URL is unset on Vercel (rare — production always sets Turso),
# the filesystem is read-only outside /tmp, so default there rather than
# under BASE_DIR (which would be inside the function bundle and unwritable).
_default_db_path = "/tmp/magic.db" if os.environ.get("VERCEL") else str(BASE_DIR / "magic.db")
DB_PATH = Path(os.environ.get("DB_PATH", _default_db_path))

# Turso (libSQL-over-HTTP) connection for serverless deployment.
# When both are set, database.py connects remotely and DB_PATH is ignored.
# URL must be the libsql:// form (not the https:// dashboard URL).
# Env var name matches Turso's documented convention.
TURSO_DATABASE_URL = os.environ.get("TURSO_DATABASE_URL")
TURSO_AUTH_TOKEN = os.environ.get("TURSO_AUTH_TOKEN")

# Templates and static asset directories.
# Static assets live under public/static/ so that Vercel serves them at /static/*
# from the CDN (Vercel only auto-serves files under public/). The /static/* URL
# prefix is unchanged for both local dev (StaticFiles mount) and Vercel.
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "public" / "static"

# Scryfall API
SCRYFALL_BASE_URL = "https://api.scryfall.com"
SCRYFALL_USER_AGENT = "MagicDeckBuilder/1.0 (local single-user app)"
SCRYFALL_MIN_DELAY = 0.15  # 150ms between requests (~6.6 req/s, under 10/s limit)

# Cache TTLs
CARD_CACHE_TTL_DAYS = 30
AUTOCOMPLETE_CACHE_TTL_SECONDS = 300  # 5 minutes
