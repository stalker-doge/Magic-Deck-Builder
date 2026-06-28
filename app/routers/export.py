"""Deck export download endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app import database as db
from app import export as export_mod

router = APIRouter(tags=["export"])


def _safe_filename(name: str) -> str:
    """Sanitize a deck name for use in a download filename."""
    keep = "-_"
    return "".join(c if c.isalnum() or c in keep else "_" for c in name) or "deck"


@router.get("/decks/{deck_id}/export/{format}")
async def export_deck(deck_id: int, format: str):
    """Download a deck in one of: txt, mtgo, csv."""
    deck = await db.get_deck(deck_id)
    if deck is None:
        raise HTTPException(status_code=404, detail="Deck not found")
    entries = await db.get_deck_entries(deck_id)

    base = _safe_filename(deck["name"])

    if format == "txt":
        content = export_mod.to_text(deck, entries)
        return Response(
            content=content,
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{base}.txt"'},
        )
    if format == "mtgo":
        content = export_mod.to_mtgo(deck, entries)
        return Response(
            content=content,
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{base}.dek"'},
        )
    if format == "csv":
        content = export_mod.to_csv(deck, entries)
        return Response(
            content=content,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{base}.csv"'},
        )
    raise HTTPException(status_code=400, detail=f"Unknown format: {format}")
