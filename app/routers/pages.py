"""HTML page routes (Jinja2 templates)."""
from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app import database as db
from app.config import TEMPLATES_DIR

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("/")
async def index(request: Request):
    """Deck list landing page."""
    decks = await db.list_decks()
    return templates.TemplateResponse(
        request, "index.html", {"decks": decks}
    )


@router.get("/decks/new")
async def new_deck_form(request: Request):
    """Form for creating a new deck."""
    return templates.TemplateResponse(
        request, "deck_form.html", {"deck": None}
    )


@router.post("/decks")
async def create_deck(
    name: str = Form(...),
    description: str = Form(""),
    format: str = Form("casual"),
):
    """Create a deck and redirect to the editor."""
    deck_id = await db.create_deck(name=name, description=description, fmt=format)
    return RedirectResponse(url=f"/decks/{deck_id}", status_code=303)


@router.get("/decks/{deck_id}")
async def deck_editor(request: Request, deck_id: int):
    """The main deck editor workspace."""
    deck = await db.get_deck(deck_id)
    if deck is None:
        raise HTTPException(status_code=404, detail="Deck not found")
    entries = await db.get_deck_entries(deck_id)
    # Group entries by section for the template.
    sections = {"main": [], "sideboard": [], "maybe": []}
    for e in entries:
        sections.setdefault(e["section"], []).append(e)
    return templates.TemplateResponse(
        request,
        "deck_editor.html",
        {
            "deck": deck,
            "sections": sections,
            "deck_json_seed": {
                "id": deck["id"],
                "name": deck["name"],
                "description": deck.get("description", ""),
                "format": deck.get("format", "casual"),
            },
        },
    )


@router.post("/decks/{deck_id}/delete")
async def delete_deck(deck_id: int):
    """Delete a deck and redirect to the deck list."""
    await db.delete_deck(deck_id)
    return RedirectResponse(url="/", status_code=303)
