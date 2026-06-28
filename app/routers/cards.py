"""Card search / autocomplete JSON endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.scryfall import scryfall

router = APIRouter(tags=["cards"])

# The five classic basic lands, keyed by MTG color code. Used by the
# deck editor's one-click "Basic Lands" toolbar.
BASIC_LANDS = {
    "W": "Plains",
    "U": "Island",
    "B": "Swamp",
    "R": "Mountain",
    "G": "Forest",
}


@router.get("/cards/search")
async def search_cards(
    q: str = Query("", description="Scryfall search query"),
    page: int = Query(1, ge=1),
):
    """Proxy to Scryfall /cards/search and cache result cards."""
    try:
        result = await scryfall.search(q, page=page)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Scryfall error: {exc}") from exc
    return result


@router.get("/cards/autocomplete")
async def autocomplete_cards(q: str = Query("", min_length=0)):
    """Return matching card names for type-ahead search."""
    if not q.strip():
        return {"names": []}
    try:
        names = await scryfall.autocomplete(q)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Scryfall error: {exc}") from exc
    return {"names": names}


@router.get("/cards/basics")
async def get_basics():
    """Return the five basic lands keyed by color code (cache-first).

    Response shape::
        {"basics": {"W": {"id","name","image_small","type_line"}, ...}}

    Any basic that can't be resolved is omitted so the toolbar simply
    renders fewer buttons rather than failing wholesale.
    """
    out = {}
    for code, name in BASIC_LANDS.items():
        card = await scryfall.get_card_by_name(name)
        if card:
            out[code] = {
                "id": card.get("id"),
                "name": card.get("name", name),
                "image_small": card.get("image_small", ""),
                "type_line": card.get("type_line", ""),
            }
    return {"basics": out}


@router.get("/cards/{card_id}")
async def get_card(card_id: str):
    """Fetch a single card by Scryfall ID (cache-first)."""
    card = await scryfall.get_card(card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Card not found")
    return card
