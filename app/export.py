"""Pure functions that serialize a deck into text/MTGO/CSV formats.

Each function takes a deck dict and an iterable of entry dicts (as produced by
``database.get_deck_entries``) and returns a string.
"""
from __future__ import annotations

import csv
import io
from typing import Iterable

SECTION_LABELS = {
    "main": "Main Deck",
    "sideboard": "Sideboard",
    "maybe": "Maybeboard",
}


def _group_by_section(entries: Iterable[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {"main": [], "sideboard": [], "maybe": []}
    for e in entries:
        section = e.get("section", "main")
        grouped.setdefault(section, []).append(e)
    # Stable sort by name within each section.
    for section, items in grouped.items():
        items.sort(key=lambda x: x.get("name", ""))
    return grouped


def to_text(deck: dict, entries: Iterable[dict]) -> str:
    """Plain text format with section headers and `count name` lines."""
    grouped = _group_by_section(entries)
    lines = [f"# {deck.get('name', 'Deck')}"]
    if deck.get("description"):
        lines.append(f"# {deck['description']}")
    lines.append("")
    for section in ("main", "sideboard", "maybe"):
        items = grouped.get(section, [])
        if not items:
            continue
        total = sum(int(i.get("quantity", 0)) for i in items)
        lines.append(f"// {SECTION_LABELS[section]} ({total})")
        for item in items:
            lines.append(f"{item['quantity']} {item['name']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def to_mtgo(deck: dict, entries: Iterable[dict]) -> str:
    """MTGO format: main deck entries, blank line, sideboard. No maybeboard."""
    grouped = _group_by_section(entries)
    lines: list[str] = []
    for item in grouped.get("main", []):
        lines.append(f"{item['quantity']} {item['name']}")
    # Only emit sideboard separator if there are sideboard cards.
    if grouped.get("sideboard"):
        lines.append("")
        for item in grouped["sideboard"]:
            lines.append(f"{item['quantity']} {item['name']}")
    return "\n".join(lines) + "\n"


def to_csv(deck: dict, entries: Iterable[dict]) -> str:
    """CSV with one row per entry. Uses csv.writer for proper escaping."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "Section",
            "Quantity",
            "Name",
            "Mana Cost",
            "CMC",
            "Type Line",
            "Colors",
            "Set",
            "Rarity",
            "Power",
            "Toughness",
        ]
    )
    grouped = _group_by_section(entries)
    for section in ("main", "sideboard", "maybe"):
        for item in grouped.get(section, []):
            colors = item.get("colors") or []
            writer.writerow(
                [
                    section,
                    item.get("quantity", 1),
                    item.get("name", ""),
                    item.get("mana_cost", ""),
                    item.get("cmc", 0),
                    item.get("type_line", ""),
                    "".join(colors),
                    item.get("set_name", ""),
                    item.get("rarity", ""),
                    item.get("power", ""),
                    item.get("toughness", ""),
                ]
            )
    return buf.getvalue()
