"""Pure functions for calculating deck statistics."""
from __future__ import annotations

from typing import Iterable

# MTG color order.
COLOR_KEYS = ("W", "U", "B", "R", "G", "C")


def _is_land(entry: dict) -> bool:
    """True if the card is a land.

    Lands produce mana rather than costing it: they have no mana cost, CMC 0,
    and (for basics) an empty ``colors`` array. Counting them would dump every
    basic land into the 0-CMC bucket and the colorless wedge of the pie,
    drowning out the spells the curve/pie are meant to describe.

    Detection is a substring match on ``type_line`` — MTG land subtypes
    (Plains, Island, …) never contain the word "Land", so this is reliable.
    A handful of transforming cards with a '// Land' back face are also
    excluded, which is an acceptable pragmatic edge case.
    """
    return "Land" in (entry.get("type_line") or "")


def calculate_mana_curve(entries: Iterable[dict]) -> dict:
    """Return a histogram of card quantities bucketed by CMC.

    Buckets: 0, 1, 2, 3, 4, 5, 6, 7+.
    Only ``main`` section entries are counted, and lands are excluded.
    """
    curve: dict = {str(i): 0 for i in range(8)}
    curve["7+"] = 0
    for e in entries:
        if e.get("section") != "main" or _is_land(e):
            continue
        try:
            cmc = int(float(e.get("cmc") or 0))
        except (TypeError, ValueError):
            cmc = 0
        qty = int(e.get("quantity") or 0)
        key = "7+" if cmc >= 7 else str(cmc)
        curve[key] += qty
    return curve


def calculate_color_distribution(entries: Iterable[dict]) -> dict:
    """Return card quantities per color (W/U/B/R/G/C).

    Colorless non-land cards (empty colors list) count toward ``C``.
    Multi-color cards count once per color in their identity.
    Only ``main`` section entries are counted, and lands are excluded
    (so 20 Mountains no longer inflate the colorless wedge).
    """
    colors = {k: 0 for k in COLOR_KEYS}
    for e in entries:
        if e.get("section") != "main" or _is_land(e):
            continue
        card_colors = e.get("colors") or []
        qty = int(e.get("quantity") or 0)
        if not card_colors:
            colors["C"] += qty
            continue
        for c in card_colors:
            if c in colors:
                colors[c] += qty
    return colors


def calculate_totals(entries: Iterable[dict]) -> dict:
    """Return total card counts per section."""
    totals = {"commander": 0, "main": 0, "sideboard": 0, "maybe": 0, "all": 0}
    for e in entries:
        qty = int(e.get("quantity") or 0)
        section = e.get("section", "main")
        if section in totals:
            totals[section] += qty
        totals["all"] += qty
    return totals


def deck_summary(entries: Iterable[dict]) -> dict:
    """Combine all stats into a single response dict."""
    entries = list(entries)
    return {
        "mana_curve": calculate_mana_curve(entries),
        "colors": calculate_color_distribution(entries),
        "totals": calculate_totals(entries),
    }
