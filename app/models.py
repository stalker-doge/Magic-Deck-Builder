"""Pydantic models for API request/response validation."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


Section = Literal["main", "sideboard", "maybe"]


class AddCardRequest(BaseModel):
    card_id: str
    section: Section = "main"
    quantity: int = Field(default=1, ge=1, le=99)


class UpdateEntryRequest(BaseModel):
    quantity: int | None = Field(default=None, ge=1, le=99)
    section: Section | None = None


class MoveEntryRequest(BaseModel):
    entry_id: int
    from_section: Section
    to_section: Section
    new_order_from: list[int] | None = None
    new_order_to: list[int] | None = None


class DeckCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    format: str = "casual"
