"""Deck-aware card recommendations.

Hybrid strategy: commander staples + theme-matched cards. Anchors on the
commander (for commander format) or main-deck cards (other formats), detects
themes from oracle text, and surfaces on-color cards not already in the deck.

Results are cached in-memory keyed by ``(deck_id, frozenset(card_ids))`` so
adding/removing a card invalidates the cache but qty/move changes hit.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from collections import OrderedDict
from typing import Any

from app.scryfall import scryfall


log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WUBRG = ("W", "U", "B", "R", "G")

# Colorless commander staples — work in any color identity.
# Fetched in a single Scryfall call via !"Name" OR !"Name" syntax.
COMMANDER_STAPLES = [
    "Sol Ring", "Arcane Signet", "Command Tower", "Mana Crypt",
    "Mana Vault", "Fellwar Stone", "Mind Stone", "Hedron Archive",
    "Thought Vessel", "Darksteel Ingot", "Commander's Sphere",
    "Wayfarer's Bauble", "Swiftfoot Boots", "Lightning Greaves",
    "Reliquary Tower", "Temple of the False God",
]

# (id, label, regex, scryfall_oracle_clause). Regex is case-insensitive.
# Tribal is intentionally omitted in v1 — creature-type detection needs its
# own pass and would over-complicate the theme list.
THEMES: list[tuple[str, str, str, str]] = [
    ("artifact",     "Artifact Synergy",  r"\bartifact",
        "o:artifact"),
    ("enchantment",  "Enchantment Synergy", r"\benchantment",
        "o:enchantment"),
    ("tokens",       "Tokens",            r"\btoken",
        'o:"create a token" OR o:tokenize OR o:"token enters"'),
    ("counters",     "+1/+1 Counters",    r"\+1/\+1 counter",
        'o:"+1/+1 counter"'),
    ("graveyard",    "Graveyard",         r"\bgraveyard\b",
        "o:graveyard"),
    ("sacrifice",    "Sacrifice",         r"\bsacrifice",
        "o:sacrifice"),
    ("spellslinger", "Spellslinger",      r"\binstant\b|\bsorcery\b|\bcast (an? )?(instant|sorcery)",
        "t:instant OR t:sorcery"),
    ("landfall",     "Lands Matter",      r"landfall|land enters the battlefield|land you control",
        'o:"land enters the battlefield" OR o:landfall OR o:"lands you control"'),
    ("draw",         "Card Draw",         r"\bdraw\b",
        'o:"draw a card" OR o:"draw cards" OR o:"card draw"'),
]

THEME_MIN_COUNT = 2       # need 2+ matches across all deck entries to surface
MAX_THEMES = 3            # never show more than 3 themes
MAX_CARDS_PER_CATEGORY = 6
MAX_EXCLUDE_NAMES = 30

# LRU cache. Key: (deck_id, frozenset(card_ids)). Value: (timestamp, payload).
_CACHE: "OrderedDict[tuple[int, frozenset[str]], tuple[float, dict]]" = OrderedDict()
_CACHE_TTL_SECONDS = 300  # 5 minutes
_CACHE_MAX_ENTRIES = 10


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------


def _anchor_cards(deck: dict, entries: list[dict]) -> list[dict]:
    """Cards that define the deck's identity and themes.

    Commander decks anchor on the commander section (falling back to main if
    no commander is set). Other formats anchor on main, then sideboard, then
    maybe — whichever has cards first.
    """
    fmt = (deck or {}).get("format", "casual")
    sections_to_try = (
        ["commander", "main"]
        if fmt == "commander"
        else ["main", "sideboard", "maybe"]
    )
    for section in sections_to_try:
        cards = [e for e in entries if e.get("section") == section]
        if cards:
            return cards
    return []


def _color_identity_union(cards: list[dict]) -> list[str]:
    """WUBRG-sorted union of all color identities in `cards`."""
    found: set[str] = set()
    for c in cards:
        for letter in (c.get("color_identity") or []):
            if letter in WUBRG:
                found.add(letter)
    return [letter for letter in WUBRG if letter in found]


def _concat_text(cards: list[dict]) -> str:
    """Lowercased name + type + oracle for theme regex matching."""
    parts: list[str] = []
    for c in cards:
        parts.append((c.get("name") or "").lower())
        parts.append((c.get("type_line") or "").lower())
        parts.append((c.get("oracle_text") or "").lower())
    return "\n".join(parts)


def _detect_themes(entries: list[dict]) -> list[tuple[str, str, str]]:
    """Return up to MAX_THEMES (id, label, clause) tuples whose regex matched
    at least THEME_MIN_COUNT times across ALL deck entries' text, ranked by
    count.

    Uses every entry (commander + main + sideboard + maybe) rather than just
    the anchor/commander, because deck composition is a stronger thematic
    signal than the commander's oracle text alone. A deck with 10 artifacts
    is an artifact deck even if the commander never says "artifact".
    """
    if not entries:
        return []
    text = _concat_text(entries)
    scored: list[tuple[int, int, str, str, str]] = []
    for order, (theme_id, label, pattern, clause) in enumerate(THEMES):
        matches = len(re.findall(pattern, text, flags=re.IGNORECASE))
        if matches >= THEME_MIN_COUNT:
            scored.append((-matches, order, theme_id, label, clause))
    # Sort: highest count first, then original definition order.
    scored.sort()
    return [(tid, label, clause) for _, _, tid, label, clause in scored[:MAX_THEMES]]


def _exclude_clause(entries: list[dict]) -> str:
    """Scryfall `-name:"X"` chain for cards already in the deck (any section).

    Names are deduped and capped at MAX_EXCLUDE_NAMES to keep queries short.
    """
    seen: set[str] = set()
    names: list[str] = []
    for e in entries:
        name = (e.get("name") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
        if len(names) >= MAX_EXCLUDE_NAMES:
            break
    if not names:
        return ""
    return " ".join(f'-name:"{n}"' for n in names)


def _identity_clause(identity: list[str]) -> str:
    """Scryfall `id<=WUB` constraint. Empty if identity is empty (no filter)."""
    if not identity:
        return ""
    return "id<=" + "".join(identity)


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


def _cache_key(deck_id: int, entries: list[dict]) -> tuple[int, frozenset[str]]:
    """Content-keyed by card_id set — qty/move changes are cache hits."""
    return (
        deck_id,
        frozenset(str(e.get("card_id")) for e in entries if e.get("card_id")),
    )


def _cache_get(key: tuple[int, frozenset[str]]) -> dict | None:
    if key not in _CACHE:
        return None
    ts, payload = _CACHE[key]
    if time.time() - ts > _CACHE_TTL_SECONDS:
        _CACHE.pop(key, None)
        return None
    _CACHE.move_to_end(key)
    return payload


def _cache_set(key: tuple[int, frozenset[str]], payload: dict) -> None:
    _CACHE[key] = (time.time(), payload)
    _CACHE.move_to_end(key)
    while len(_CACHE) > _CACHE_MAX_ENTRIES:
        _CACHE.popitem(last=False)


# ---------------------------------------------------------------------------
# Scryfall query building
# ---------------------------------------------------------------------------


def _build_theme_query(
    clause: str, identity_clause: str, exclude_clause: str
) -> str:
    """Assemble a Scryfall query for a theme category.

    Limited to permanent card types — instants/sorceries are surfaced via
    the spellslinger theme rather than every theme.
    """
    type_clause = (
        "(t:creature OR t:artifact OR t:enchantment "
        "OR t:planeswalker OR t:battle)"
    )
    parts = [f"({clause})", type_clause]
    if identity_clause:
        parts.append(identity_clause)
    if exclude_clause:
        parts.append(exclude_clause)
    return " ".join(parts)


async def _fetch_staples(identity: list[str]) -> list[dict]:
    """Fetch commander staples via cached name lookups, filtered to identity.

    Uses ``scryfall.get_card_by_name`` (DB-cached for 30 days) instead of a
    single bulk search, because Scryfall's ``/cards/search`` does not accept
    the ``!"Name"`` exact-name operator reliably across multi-clause OR
    queries. The 16 lookups fire concurrently; the Scryfall client's
    150ms rate limiter serializes them (~2.4s on first miss, instant on
    subsequent calls via the SQLite card cache).
    """
    id_set = set(identity)

    async def fetch(name: str) -> dict | None:
        try:
            return await scryfall.get_card_by_name(name)
        except Exception as exc:  # noqa: BLE001
            log.warning("Staple lookup failed for %r: %s", name, exc)
            return None

    results = await asyncio.gather(*(fetch(n) for n in COMMANDER_STAPLES))
    return [
        c for c in results
        if c is not None
        and set(c.get("color_identity") or []).issubset(id_set)
    ]


# ---------------------------------------------------------------------------
# I/O orchestration
# ---------------------------------------------------------------------------


async def _safe_search(query: str) -> list[dict]:
    """Run a Scryfall search, returning [] on any error."""
    try:
        result = await scryfall.search(query)
        return result.get("cards", [])
    except Exception as exc:  # noqa: BLE001
        log.warning("Recommendation search failed for %r: %s", query, exc)
        return []


async def build_recommendations(deck: dict, entries: list[dict]) -> dict:
    """Top-level recommendations entry point.

    Returns::

        {
          "format": "commander",
          "color_identity": ["W", "U"],
          "categories": [
            {"id": "staples", "label": "Staples", "cards": [...]},
            {"id": "artifact", "label": "Artifact Synergy", "cards": [...]},
            ...
          ]
        }

    Empty decks return ``{"format": ..., "categories": [], "reason": "empty"}``.
    """
    deck_id = (deck or {}).get("id")
    if deck_id is None:
        return {
            "format": "casual",
            "color_identity": [],
            "categories": [],
            "reason": "no_deck",
        }

    key = _cache_key(int(deck_id), entries)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    fmt = (deck or {}).get("format", "casual")
    anchors = _anchor_cards(deck, entries)
    if not anchors:
        payload = {
            "format": fmt,
            "color_identity": [],
            "categories": [],
            "reason": "empty",
        }
        _cache_set(key, payload)
        return payload

    identity = _color_identity_union(anchors)
    identity_clause = _identity_clause(identity)
    exclude_clause = _exclude_clause(entries)
    # Themes are detected from the FULL deck composition, not just the
    # commander — a deck with 10 artifacts is an artifact deck regardless
    # of what the commander's oracle text says.
    themes = _detect_themes(entries)

    # Build the (category_id, label, awaitable) tasks to fan out. Staples
    # use _fetch_staples (cached name lookups); themes use _safe_search.
    tasks: list[tuple[str, str, Any]] = []
    if fmt == "commander":
        tasks.append(("staples", "Staples", _fetch_staples(identity)))
    for theme_id, label, clause in themes:
        query = _build_theme_query(clause, identity_clause, exclude_clause)
        tasks.append((theme_id, label, _safe_search(query)))

    # Fan out all tasks concurrently. The Scryfall client serializes the
    # actual HTTP calls (150ms rate limit), but concurrent scheduling keeps
    # the code simple and lets multiple misses overlap.
    if tasks:
        results = await asyncio.gather(*(t[2] for t in tasks))
    else:
        results = []

    # Dedupe across categories: first occurrence wins. Staples come first.
    seen_ids: set[str] = set()
    categories: list[dict] = []
    for (cat_id, label, _), cards in zip(tasks, results):
        picked: list[dict] = []
        for c in cards:
            cid = c.get("id")
            if cid is None or cid in seen_ids:
                continue
            seen_ids.add(cid)
            picked.append(c)
            if len(picked) >= MAX_CARDS_PER_CATEGORY:
                break
        if picked:
            categories.append({"id": cat_id, "label": label, "cards": picked})

    payload = {
        "format": fmt,
        "color_identity": identity,
        "categories": categories,
    }
    _cache_set(key, payload)
    return payload
