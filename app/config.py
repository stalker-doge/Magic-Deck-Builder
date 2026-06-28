"""Application configuration."""
from pathlib import Path

# Project root (parent of the app/ directory)
BASE_DIR = Path(__file__).resolve().parent.parent

# SQLite database file
DB_PATH = BASE_DIR / "magic.db"

# Templates and static asset directories
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

# Scryfall API
SCRYFALL_BASE_URL = "https://api.scryfall.com"
SCRYFALL_USER_AGENT = "MagicDeckBuilder/1.0 (local single-user app)"
SCRYFALL_MIN_DELAY = 0.15  # 150ms between requests (~6.6 req/s, under 10/s limit)

# Cache TTLs
CARD_CACHE_TTL_DAYS = 30
AUTOCOMPLETE_CACHE_TTL_SECONDS = 300  # 5 minutes
