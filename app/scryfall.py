"""Async Scryfall API client with rate limiting, retries, and caching.

Scryfall asks for a 50-100ms delay between requests and provides a hard 10 req/s
limit. We use 150ms to be safe. Card objects are cached in the local SQLite
database for 30 days to avoid re-fetching.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import httpx

from app import database as db
from app.config import (
    AUTOCOMPLETE_CACHE_TTL_SECONDS,
    CARD_CACHE_TTL_DAYS,
    SCRYFALL_BASE_URL,
    SCRYFALL_MIN_DELAY,
    SCRYFALL_USER_AGENT,
)


# ---------------------------------------------------------------------------
# Card normalization
# ---------------------------------------------------------------------------


def normalize_card(raw: dict) -> dict:
    """Convert a raw Scryfall card object into a DB-ready dict.

    Handles multi-faced cards (transform, modal DFCs) by falling back to the
    first face for fields that are only present at the top level on single-face
    cards.
    """
    card_faces = raw.get("card_faces") or []
    has_faces = len(card_faces) > 1

    def first_face_field(key: str, default: str = "") -> str:
        if raw.get(key):
            return raw[key]
        if has_faces and card_faces[0].get(key):
            return card_faces[0][key]
        return default

    # Image URis: top-level preferred; otherwise first face.
    image_uris = raw.get("image_uris") or {}
    if not image_uris and has_faces:
        image_uris = card_faces[0].get("image_uris") or {}

    # Oracle text: join faces with separator for multi-face cards.
    oracle = raw.get("oracle_text") or ""
    if not oracle and has_faces:
        oracle = "\n—\n".join(
            f"{f.get('name', '')}: {f.get('oracle_text', '')}".strip(": ")
            for f in card_faces
            if f.get("oracle_text")
        )

    return {
        "id": raw["id"],
        "name": raw.get("name", ""),
        "mana_cost": first_face_field("mana_cost"),
        "cmc": float(raw.get("cmc") or 0),
        "type_line": first_face_field("type_line"),
        "oracle_text": oracle,
        "colors": json.dumps(raw.get("colors") or []),
        "color_identity": json.dumps(raw.get("color_identity") or []),
        "image_small": image_uris.get("small", ""),
        "image_normal": image_uris.get("normal", ""),
        "image_png": image_uris.get("png", ""),
        "set_name": raw.get("set_name", ""),
        "set_code": raw.get("set", ""),
        "rarity": raw.get("rarity", ""),
        "power": str(raw.get("power") or ""),
        "toughness": str(raw.get("toughness") or ""),
        "layout": raw.get("layout", "normal"),
        "card_faces_json": json.dumps(card_faces),
        "scryfall_uri": raw.get("scryfall_uri", ""),
    }


def card_from_raw(raw: dict) -> dict:
    """Normalize + decode JSON list fields for API responses."""
    card = normalize_card(raw)
    out = dict(card)
    out["colors"] = json.loads(card["colors"])
    out["color_identity"] = json.loads(card["color_identity"])
    out["card_faces"] = json.loads(card["card_faces_json"])
    return out


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class ScryfallClient:
    """Singleton async Scryfall client with throttling and caching."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._last_request_at: float = 0.0
        self._lock = asyncio.Lock()
        self._autocomplete_cache: dict[str, tuple[float, list[str]]] = {}

    async def get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=SCRYFALL_BASE_URL,
                headers={"User-Agent": SCRYFALL_USER_AGENT},
                timeout=httpx.Timeout(10.0, connect=5.0),
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    # -- low-level request with throttle + retry --

    async def _get(self, path: str, params: dict | None = None) -> dict | None:
        """Issue a throttled GET with retry on 429. Returns None on 404."""
        async with self._lock:
            elapsed = time.monotonic() - self._last_request_at
            if elapsed < SCRYFALL_MIN_DELAY:
                await asyncio.sleep(SCRYFALL_MIN_DELAY - elapsed)

            client = await self.get_client()
            last_exc: Exception | None = None
            for attempt in range(3):
                try:
                    resp = await client.get(path, params=params)
                except httpx.HTTPError as exc:
                    last_exc = exc
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue

                self._last_request_at = time.monotonic()

                if resp.status_code == 404:
                    return None
                if resp.status_code == 429:
                    # Respect Retry-After if present, else exponential backoff.
                    retry_after = resp.headers.get("Retry-After")
                    delay = (
                        float(retry_after)
                        if retry_after
                        else 1.0 * (attempt + 1)
                    )
                    await asyncio.sleep(delay)
                    continue
                resp.raise_for_status()
                return resp.json()

            if last_exc:
                raise last_exc
            raise RuntimeError(f"Scryfall request failed for {path}")

    # -- search --

    async def search(
        self, query: str, page: int = 1, unique: str = "cards"
    ) -> dict:
        """Search cards. Returns normalized cards and pagination info."""
        if not query.strip():
            return {
                "cards": [],
                "total_cards": 0,
                "has_more": False,
                "next_page": None,
            }
        data = await self._get(
            "/cards/search",
            params={"q": query, "page": page, "unique": unique},
        )
        if data is None:
            return {
                "cards": [],
                "total_cards": 0,
                "has_more": False,
                "next_page": None,
            }

        raw_cards = data.get("data", [])
        cards: list[dict] = []
        for raw in raw_cards:
            card = card_from_raw(raw)
            # Cache for future lookups.
            try:
                await db.upsert_card(normalize_card(raw))
            except Exception as exc:  # noqa: BLE001
                import logging
                logging.getLogger(__name__).warning(
                    "Failed to cache card %s: %s", raw.get("id"), exc
                )
            cards.append(card)
        return {
            "cards": cards,
            "total_cards": data.get("total_cards", len(cards)),
            "has_more": bool(data.get("has_more")),
            "next_page": data.get("next_page"),
        }

    # -- autocomplete --

    async def autocomplete(self, query: str) -> list[str]:
        """Return card name completions. Cached for 5 minutes in memory."""
        q = query.strip()
        if not q:
            return []
        cached = self._autocomplete_cache.get(q)
        if cached and time.time() - cached[0] < AUTOCOMPLETE_CACHE_TTL_SECONDS:
            return cached[1]

        data = await self._get("/cards/autocomplete", params={"q": q})
        names = (data or {}).get("data", [])
        self._autocomplete_cache[q] = (time.time(), names)
        # Bounded cache: drop oldest entries if it grows too large.
        if len(self._autocomplete_cache) > 200:
            oldest = sorted(
                self._autocomplete_cache.items(), key=lambda kv: kv[1][0]
            )
            for k, _ in oldest[:50]:
                self._autocomplete_cache.pop(k, None)
        return names

    # -- single card --

    async def get_card(self, card_id: str) -> dict | None:
        """Get a card by Scryfall ID, using the SQLite cache when fresh."""
        cached = await db.get_cached_card(card_id, CARD_CACHE_TTL_DAYS)
        if cached:
            return cached
        data = await self._get(f"/cards/{card_id}")
        if data is None:
            # Fall back to a stale cache row if present.
            return await db.get_cached_card_by_id(card_id)
        try:
            await db.upsert_card(normalize_card(data))
        except Exception:
            pass
        return card_from_raw(data)

    async def get_card_by_name(self, name: str) -> dict | None:
        """Fetch a card by exact/fuzzy name. Used for text-import (future)."""
        if not name.strip():
            return None
        data = await self._get("/cards/named", params={"fuzzy": name})
        if data is None:
            return None
        try:
            await db.upsert_card(normalize_card(data))
        except Exception:
            pass
        return card_from_raw(data)


# Singleton instance shared by routers.
scryfall = ScryfallClient()
