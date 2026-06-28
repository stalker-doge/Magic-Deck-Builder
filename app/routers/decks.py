"""Deck and deck-entry JSON endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app import database as db
from app.commander import deck_legality_report
from app.models import AddCardRequest, MoveEntryRequest, UpdateEntryRequest
from app.recommend import build_recommendations
from app.stats import deck_summary

router = APIRouter(tags=["decks"])


@router.post("/decks/{deck_id}/cards")
async def add_card(deck_id: int, payload: AddCardRequest):
    """Add a card to a deck section, incrementing quantity if present."""
    deck = await db.get_deck(deck_id)
    if deck is None:
        raise HTTPException(status_code=404, detail="Deck not found")
    entry = await db.add_card_to_deck(
        deck_id, payload.card_id, payload.section, payload.quantity
    )
    return entry


@router.patch("/decks/{deck_id}/entries/{entry_id}")
async def update_entry(deck_id: int, entry_id: int, payload: UpdateEntryRequest):
    """Update an entry's quantity and/or section."""
    existing = await db.get_entry(deck_id, entry_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Entry not found")
    await db.update_entry(
        deck_id,
        entry_id,
        quantity=payload.quantity,
        section=payload.section,
    )
    return {"ok": True}


@router.delete("/decks/{deck_id}/entries/{entry_id}")
async def delete_entry(deck_id: int, entry_id: int):
    """Remove an entry from a deck."""
    existing = await db.get_entry(deck_id, entry_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Entry not found")
    await db.delete_entry(deck_id, entry_id)
    return {"ok": True}


@router.post("/decks/{deck_id}/move")
async def move_entry(deck_id: int, payload: MoveEntryRequest):
    """Move an entry across sections and/or re-order within a section.

    Used by the SortableJS drag-and-drop handler on the frontend.
    """
    existing = await db.get_entry(deck_id, payload.entry_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Entry not found")
    await db.move_entry(
        deck_id,
        payload.entry_id,
        payload.to_section,
        new_order_from=payload.new_order_from,
        new_order_to=payload.new_order_to,
    )
    return {"ok": True}


@router.get("/decks/{deck_id}/stats")
async def get_stats(deck_id: int):
    """Return aggregated stats for the deck."""
    deck = await db.get_deck(deck_id)
    if deck is None:
        raise HTTPException(status_code=404, detail="Deck not found")
    entries = await db.get_deck_entries(deck_id)
    return deck_summary(entries)


@router.get("/decks/{deck_id}/entries")
async def get_entries(deck_id: int):
    """Return all entries for a deck with full card data."""
    deck = await db.get_deck(deck_id)
    if deck is None:
        raise HTTPException(status_code=404, detail="Deck not found")
    entries = await db.get_deck_entries(deck_id)
    return {"entries": entries}


@router.get("/decks/{deck_id}/legality")
async def get_legality(deck_id: int):
    """Return a Commander-format legality report for the deck.

    Non-commander formats return a no-op ``{format, legal: True, checks: {}}``.
    """
    deck = await db.get_deck(deck_id)
    if deck is None:
        raise HTTPException(status_code=404, detail="Deck not found")
    entries = await db.get_deck_entries(deck_id)
    return deck_legality_report(deck, entries)


@router.get("/decks/{deck_id}/recommendations")
async def get_recommendations(deck_id: int):
    """Return deck-aware card recommendations.

    Hybrid: commander staples (commander format only) + theme-matched cards
    detected from anchor-card oracle text. Cached in-memory keyed by the
    deck's card-id set, so adding/removing a card invalidates but qty/move
    changes are cache hits.
    """
    deck = await db.get_deck(deck_id)
    if deck is None:
        raise HTTPException(status_code=404, detail="Deck not found")
    entries = await db.get_deck_entries(deck_id)
    return await build_recommendations(deck, entries)
