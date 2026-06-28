"""SQLite database connection, schema, and query helpers.

All functions are async and use aiosqlite. The database file is created at
``config.DB_PATH`` on first use. A module-level connection is opened lazily
and reused for the lifetime of the process.
"""
from __future__ import annotations

import json
import time
from typing import Any, Iterable

import aiosqlite

from app.config import DB_PATH

# SQL for schema creation. Executed on app startup.
SCHEMA = """
CREATE TABLE IF NOT EXISTS decks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    format      TEXT NOT NULL DEFAULT 'casual',
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS cards (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    mana_cost       TEXT NOT NULL DEFAULT '',
    cmc             REAL NOT NULL DEFAULT 0,
    type_line       TEXT NOT NULL DEFAULT '',
    oracle_text     TEXT NOT NULL DEFAULT '',
    colors          TEXT NOT NULL DEFAULT '[]',
    color_identity  TEXT NOT NULL DEFAULT '[]',
    image_small     TEXT NOT NULL DEFAULT '',
    image_normal    TEXT NOT NULL DEFAULT '',
    image_png       TEXT NOT NULL DEFAULT '',
    set_name        TEXT NOT NULL DEFAULT '',
    set_code        TEXT NOT NULL DEFAULT '',
    rarity          TEXT NOT NULL DEFAULT '',
    power           TEXT NOT NULL DEFAULT '',
    toughness       TEXT NOT NULL DEFAULT '',
    layout          TEXT NOT NULL DEFAULT 'normal',
    card_faces_json TEXT NOT NULL DEFAULT '[]',
    scryfall_uri    TEXT NOT NULL DEFAULT '',
    cached_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS deck_card_entries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    deck_id     INTEGER NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
    card_id     TEXT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    section     TEXT NOT NULL DEFAULT 'main',
    quantity    INTEGER NOT NULL DEFAULT 1,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    UNIQUE(deck_id, card_id, section)
);

CREATE INDEX IF NOT EXISTS idx_entries_deck ON deck_card_entries(deck_id);
CREATE INDEX IF NOT EXISTS idx_entries_section ON deck_card_entries(deck_id, section);
CREATE INDEX IF NOT EXISTS idx_cards_name ON cards(name);
"""


# ---------------------------------------------------------------------------
# Connection management
# ---------------------------------------------------------------------------

_db: aiosqlite.Connection | None = None


async def get_db() -> aiosqlite.Connection:
    """Return the singleton database connection, opening it if needed."""
    global _db
    if _db is None:
        _db = await aiosqlite.connect(str(DB_PATH))
        _db.row_factory = aiosqlite.Row
        await _db.execute("PRAGMA foreign_keys = ON")
        await _db.commit()
    return _db


async def init_db() -> None:
    """Create tables and indexes if they don't exist."""
    db = await get_db()
    await db.executescript(SCHEMA)
    await db.commit()


async def close_db() -> None:
    """Close the database connection (used in tests / shutdown)."""
    global _db
    if _db is not None:
        await _db.close()
        _db = None


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------


async def execute(sql: str, params: Any = ()) -> Any:
    """Execute a single SQL statement and commit.

    Accepts a sequence (for ? placeholders) or a dict (for :name placeholders).
    """
    db = await get_db()
    cur = await db.execute(sql, params)
    await db.commit()
    return cur


async def executemany(sql: str, params: Iterable[Iterable[Any]]) -> Any:
    """Execute many and commit."""
    db = await get_db()
    cur = await db.executemany(sql, [tuple(p) for p in params])
    await db.commit()
    return cur


async def fetchone(sql: str, params: Any = ()) -> dict | None:
    """Fetch a single row as a dict (or None)."""
    db = await get_db()
    cur = await db.execute(sql, params)
    row = await cur.fetchone()
    return dict(row) if row else None


async def fetchall(sql: str, params: Any = ()) -> list[dict]:
    """Fetch all rows as a list of dicts."""
    db = await get_db()
    cur = await db.execute(sql, params)
    rows = await cur.fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Card cache helpers
# ---------------------------------------------------------------------------


async def upsert_card(card: dict) -> None:
    """Insert or replace a card in the cache."""
    await execute(
        """
        INSERT OR REPLACE INTO cards (
            id, name, mana_cost, cmc, type_line, oracle_text, colors,
            color_identity, image_small, image_normal, image_png,
            set_name, set_code, rarity, power, toughness, layout,
            card_faces_json, scryfall_uri, cached_at
        ) VALUES (
            :id, :name, :mana_cost, :cmc, :type_line, :oracle_text, :colors,
            :color_identity, :image_small, :image_normal, :image_png,
            :set_name, :set_code, :rarity, :power, :toughness, :layout,
            :card_faces_json, :scryfall_uri, datetime('now')
        )
        """,
        card,
    )


async def get_cached_card(card_id: str, max_age_days: int) -> dict | None:
    """Return a cached card if it exists and is fresh enough, else None."""
    row = await fetchone(
        f"""
        SELECT * FROM cards
        WHERE id = ? AND cached_at >= datetime('now', '-{int(max_age_days)} days')
        """,
        (card_id,),
    )
    if row:
        return _decode_card_row(row)
    return None


async def get_cached_card_by_id(card_id: str) -> dict | None:
    """Return any cached card regardless of age (for deck rendering)."""
    row = await fetchone("SELECT * FROM cards WHERE id = ?", (card_id,))
    if row:
        return _decode_card_row(row)
    return None


async def get_cached_card_by_name(name: str) -> dict | None:
    """Return any cached card with the exact given name, regardless of age.

    Used for stable, evergreen cards (e.g. basic lands) where any cached
    printing is acceptable and a Scryfall round-trip should be avoided.
    Case-insensitive to match Scryfall's behavior.
    """
    row = await fetchone(
        "SELECT * FROM cards WHERE name = ? COLLATE NOCASE LIMIT 1",
        (name,),
    )
    if row:
        return _decode_card_row(row)
    return None


def _decode_card_row(row: dict) -> dict:
    """Decode JSON-encoded list fields back to Python lists."""
    row["colors"] = json.loads(row.get("colors") or "[]")
    row["color_identity"] = json.loads(row.get("color_identity") or "[]")
    row["card_faces"] = json.loads(row.get("card_faces_json") or "[]")
    return row


# ---------------------------------------------------------------------------
# Deck helpers
# ---------------------------------------------------------------------------


async def create_deck(name: str, description: str, fmt: str) -> int:
    """Create a new deck and return its ID."""
    cur = await execute(
        "INSERT INTO decks (name, description, format) VALUES (?, ?, ?)",
        (name, description, fmt),
    )
    return cur.lastrowid


async def get_deck(deck_id: int) -> dict | None:
    return await fetchone("SELECT * FROM decks WHERE id = ?", (deck_id,))


async def list_decks() -> list[dict]:
    """Return all decks with per-section card counts."""
    return await fetchall(
        """
        SELECT d.*,
            COALESCE(SUM(CASE WHEN e.section = 'main' THEN e.quantity ELSE 0 END), 0) AS main_count,
            COALESCE(SUM(CASE WHEN e.section = 'sideboard' THEN e.quantity ELSE 0 END), 0) AS sideboard_count,
            COALESCE(SUM(CASE WHEN e.section = 'maybe' THEN e.quantity ELSE 0 END), 0) AS maybe_count
        FROM decks d
        LEFT JOIN deck_card_entries e ON e.deck_id = d.id
        GROUP BY d.id
        ORDER BY d.updated_at DESC
        """
    )


async def delete_deck(deck_id: int) -> None:
    await execute("DELETE FROM decks WHERE id = ?", (deck_id,))


async def touch_deck(deck_id: int) -> None:
    """Update a deck's updated_at timestamp."""
    await execute(
        "UPDATE decks SET updated_at = datetime('now') WHERE id = ?",
        (deck_id,),
    )


# ---------------------------------------------------------------------------
# Deck entry helpers
# ---------------------------------------------------------------------------

SECTIONS = ("main", "sideboard", "maybe")


async def add_card_to_deck(
    deck_id: int, card_id: str, section: str, quantity: int
) -> dict:
    """Add a card to a deck section, incrementing quantity if it exists.

    Returns the entry row.
    """
    if section not in SECTIONS:
        raise ValueError(f"invalid section: {section}")
    existing = await fetchone(
        "SELECT * FROM deck_card_entries WHERE deck_id = ? AND card_id = ? AND section = ?",
        (deck_id, card_id, section),
    )
    if existing:
        new_qty = existing["quantity"] + quantity
        await execute(
            "UPDATE deck_card_entries SET quantity = ? WHERE id = ?",
            (new_qty, existing["id"]),
        )
        existing["quantity"] = new_qty
        return existing

    # New entry: place it at the end of the section.
    max_order = await fetchone(
        "SELECT COALESCE(MAX(sort_order), -1) AS m FROM deck_card_entries WHERE deck_id = ? AND section = ?",
        (deck_id, section),
    )
    next_order = (max_order["m"] if max_order else -1) + 1
    cur = await execute(
        """
        INSERT INTO deck_card_entries (deck_id, card_id, section, quantity, sort_order)
        VALUES (?, ?, ?, ?, ?)
        """,
        (deck_id, card_id, section, quantity, next_order),
    )
    await touch_deck(deck_id)
    return {"id": cur.lastrowid, "deck_id": deck_id, "card_id": card_id,
            "section": section, "quantity": quantity, "sort_order": next_order}


async def update_entry(
    deck_id: int,
    entry_id: int,
    *,
    quantity: int | None = None,
    section: str | None = None,
) -> None:
    """Update an entry's quantity and/or section."""
    if section is not None and section not in SECTIONS:
        raise ValueError(f"invalid section: {section}")
    fields = []
    params: list[Any] = []
    if quantity is not None:
        fields.append("quantity = ?")
        params.append(quantity)
    if section is not None:
        fields.append("section = ?")
        params.append(section)
    if not fields:
        return
    params.extend([entry_id, deck_id])
    await execute(
        f"UPDATE deck_card_entries SET {', '.join(fields)} WHERE id = ? AND deck_id = ?",
        params,
    )
    await touch_deck(deck_id)


async def delete_entry(deck_id: int, entry_id: int) -> None:
    await execute(
        "DELETE FROM deck_card_entries WHERE id = ? AND deck_id = ?",
        (entry_id, deck_id),
    )
    await touch_deck(deck_id)


async def move_entry(
    deck_id: int,
    entry_id: int,
    to_section: str,
    new_order_from: list[int] | None = None,
    new_order_to: list[int] | None = None,
) -> None:
    """Move an entry to a (possibly different) section and re-apply ordering.

    ``new_order_from`` is the desired entry-id ordering for the source section
    (after the item has been removed). ``new_order_to`` is the desired ordering
    for the destination section (after the item has been added). Either may be
    None if no reordering is needed for that section.
    """
    if to_section not in SECTIONS:
        raise ValueError(f"invalid section: {to_section}")

    db = await get_db()
    try:
        await db.execute(
            "UPDATE deck_card_entries SET section = ? WHERE id = ? AND deck_id = ?",
            (to_section, entry_id, deck_id),
        )
        if new_order_from is not None:
            for idx, eid in enumerate(new_order_from):
                await db.execute(
                    "UPDATE deck_card_entries SET sort_order = ? WHERE id = ? AND deck_id = ?",
                    (idx, eid, deck_id),
                )
        if new_order_to is not None:
            for idx, eid in enumerate(new_order_to):
                await db.execute(
                    "UPDATE deck_card_entries SET sort_order = ? WHERE id = ? AND deck_id = ?",
                    (idx, eid, deck_id),
                )
        await db.execute(
            "UPDATE decks SET updated_at = datetime('now') WHERE id = ?", (deck_id,)
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise


async def get_deck_entries(deck_id: int) -> list[dict]:
    """Return all entries for a deck with full card data joined, ordered."""
    rows = await fetchall(
        """
        SELECT e.id, e.deck_id, e.card_id, e.section, e.quantity, e.sort_order,
               c.name, c.mana_cost, c.cmc, c.type_line, c.oracle_text,
               c.colors, c.color_identity, c.image_small, c.image_normal,
               c.image_png, c.set_name, c.set_code, c.rarity, c.power,
               c.toughness, c.layout, c.card_faces_json, c.scryfall_uri
        FROM deck_card_entries e
        JOIN cards c ON c.id = e.card_id
        WHERE e.deck_id = ?
        ORDER BY e.section, e.sort_order, c.name
        """,
        (deck_id,),
    )
    for r in rows:
        r["colors"] = json.loads(r.get("colors") or "[]")
        r["color_identity"] = json.loads(r.get("color_identity") or "[]")
        r["card_faces"] = json.loads(r.get("card_faces_json") or "[]")
    return rows


async def get_entry(deck_id: int, entry_id: int) -> dict | None:
    return await fetchone(
        "SELECT * FROM deck_card_entries WHERE id = ? AND deck_id = ?",
        (entry_id, deck_id),
    )


# Re-export timestamp helper for stats module.
def now_ts() -> float:
    return time.time()
