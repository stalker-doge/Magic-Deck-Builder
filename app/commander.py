"""Pure functions for evaluating Commander-format deck legality (MTG rules 903.x).

All functions here are pure: inputs are plain dicts shaped like the rows
returned by ``database.get_deck_entries`` (with ``color_identity`` / ``colors``
already decoded to lists). No I/O, no ``await``. This keeps the ruleset
trivially unit-testable.

Commander rules modelled:
- 1 commander (legendary creature, or a planeswalker whose oracle text says
  "can be your commander"), OR 2 commanders via the Partner / Partner with /
  Background / Friends forever mechanics.
- Exactly 100 cards total counting the commander(s): commander + main == 100.
- Singleton: at most 1 of any non-basic card BY NAME across commander + main +
  sideboard. Basic lands are exempt. Maybeboard is scratch (never enforced).
- Color identity: every card in commander + main + sideboard must have
  ``color_identity`` that is a subset of the commander's identity (union of
  both commanders for a pair). Basics are NOT exempt (Plains has identity W).
"""
from __future__ import annotations

import re

# Canonical MTG color order, colorless last.
WUBRG = ("W", "U", "B", "R", "G")
# Sections in which singleton + color-identity are enforced. Maybeboard excluded.
ENFORCED_SECTIONS = ("commander", "main", "sideboard")

# Regex extracting the named partner from "Partner with Pir, Imaginative Rascal".
# Scryfall oracle text uses "(suffix)" for reminder text; capture stops there.
_PARTNER_WITH_RE = re.compile(r"^Partner with (.+?)\s*(?:\(|$)", re.MULTILINE)


# ---------------------------------------------------------------------------
# Basic helpers
# ---------------------------------------------------------------------------


def _is_basic_land(card: dict) -> bool:
    """True if the card has the Basic supertype and is a Land.

    The supertype check is the source of truth (covers snow-covered basics and
    Wastes), rather than a name allowlist.
    """
    type_line = card.get("type_line") or ""
    return "Basic" in type_line and "Land" in type_line


# ---------------------------------------------------------------------------
# Commander eligibility
# ---------------------------------------------------------------------------


def can_be_commander(card: dict) -> bool:
    """True if the card may serve as a commander on its own.

    A legendary creature, or a planeswalker whose oracle text explicitly says
    "can be your commander". Substring checks on ``type_line`` are intentional
    — they also handle ``//``-joined faces of DFCs.
    """
    type_line = card.get("type_line") or ""
    oracle = card.get("oracle_text") or ""
    is_legendary_creature = "Legendary" in type_line and "Creature" in type_line
    is_eligible_walker = (
        "Planeswalker" in type_line and "can be your commander" in oracle
    )
    return is_legendary_creature or is_eligible_walker


# ---------------------------------------------------------------------------
# Partner / Background / Friends forever keyword detection
# ---------------------------------------------------------------------------


def _has_standalone_keyword(oracle: str, keyword: str) -> bool:
    """True if ``keyword`` appears as a standalone ability word on its own line.

    "Partner with X" must NOT match when checking for the bare "Partner"
    keyword, since the former is a distinct mechanic.
    """
    for line in oracle.split("\n"):
        stripped = line.strip()
        if stripped == keyword or stripped.startswith(keyword + "."):
            return True
        if stripped.startswith(keyword + " "):
            rest = stripped[len(keyword):].strip()
            # For "Partner", "Partner with ..." is a different keyword.
            if keyword == "Partner" and rest.lower().startswith("with"):
                continue
            return True
    return False


def _partner_kind(card: dict) -> str:
    """Classify the card's commander-pairing mechanic.

    Returns one of: ``"none"``, ``"partner"``, ``"partner_with"``,
    ``"background"``, ``"friends_forever"``.

    Order-sensitive: "Partner with" is checked BEFORE the bare "Partner"
    keyword, because the latter is a substring of the former.

    Note: "Background" is a card subtype (``Enchantment — Background``), not an
    oracle keyword — it's detected from ``type_line``. A Background enchantment
    pairs with any legendary creature as a second commander.
    """
    oracle = card.get("oracle_text") or ""
    type_line = card.get("type_line") or ""
    # "Partner with [Name]" — detect first.
    if _PARTNER_WITH_RE.search(oracle):
        return "partner_with"
    if _has_standalone_keyword(oracle, "Partner"):
        return "partner"
    if _has_standalone_keyword(oracle, "Friends forever"):
        return "friends_forever"
    if "Background" in type_line:
        return "background"
    return "none"


def _partner_with_name(card: dict) -> str | None:
    """Return the target card name for a "Partner with X" card, else None."""
    match = _PARTNER_WITH_RE.search(card.get("oracle_text") or "")
    if not match:
        return None
    return match.group(1).strip().rstrip(".")


def _is_legendary_creature(card: dict) -> bool:
    type_line = card.get("type_line") or ""
    return "Legendary" in type_line and "Creature" in type_line


def commander_pair_legal(a: dict, b: dict) -> bool:
    """True if two cards may serve together as a commander pair."""
    ka, kb = _partner_kind(a), _partner_kind(b)

    # Background: one legendary creature + one Background keyword card.
    if ka == "background" and _is_legendary_creature(b):
        return True
    if kb == "background" and _is_legendary_creature(a):
        return True

    # Partner with [Name]: pairs only with the named card.
    if ka == "partner_with":
        target = _partner_with_name(a)
        return (
            target is not None
            and target.lower() == (b.get("name") or "").lower()
        )
    if kb == "partner_with":
        target = _partner_with_name(b)
        return (
            target is not None
            and target.lower() == (a.get("name") or "").lower()
        )

    # Generic Partner pairs with Partner or Friends forever.
    if ka == "partner" and kb in ("partner", "friends_forever"):
        return True
    if kb == "partner" and ka in ("partner", "friends_forever"):
        return True

    # Friends forever pairs with Friends forever or Partner.
    if ka == "friends_forever" and kb in ("friends_forever", "partner"):
        return True
    if kb == "friends_forever" and ka in ("friends_forever", "partner"):
        return True

    return False


def _describe_pairing(a: dict, b: dict) -> str | None:
    """Human-readable pairing label for a legal pair, else None."""
    ka, kb = _partner_kind(a), _partner_kind(b)
    if ka == "partner_with" or kb == "partner_with":
        return "partner_with"
    if ka == "background" or kb == "background":
        return "background"
    if ka == "friends_forever" or kb == "friends_forever":
        return "friends_forever"
    if ka == "partner" or kb == "partner":
        return "partner"
    return None


# ---------------------------------------------------------------------------
# Color identity
# ---------------------------------------------------------------------------


def commander_color_identity(commander_entries: list[dict]) -> list[str]:
    """Return the union of the commanders' color identities, WUBRG-ordered."""
    union: set[str] = set()
    for card in commander_entries:
        for col in card.get("color_identity") or []:
            union.add(col)
    order = {c: i for i, c in enumerate(list(WUBRG) + ["C"])}
    return sorted(union, key=lambda c: order.get(c, 99))


def color_identity_violations(allowed: list[str], entries: list[dict]) -> list[dict]:
    """Return cards whose color_identity is not a subset of ``allowed``.

    Basics are NOT exempt (official rule: a Plains has identity W and is illegal
    in a non-W commander deck). Only commander/main/sideboard are checked.
    """
    allowed_set = set(allowed or [])
    out: list[dict] = []
    for e in entries:
        if e.get("section") not in ENFORCED_SECTIONS:
            continue
        identity = set(e.get("color_identity") or [])
        if not identity.issubset(allowed_set):
            out.append({
                "name": e.get("name") or "",
                "card_id": e.get("card_id"),
                "entry_id": e.get("id"),
                "color_identity": sorted(identity),
                "excess": sorted(identity - allowed_set),
            })
    return out


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


def singleton_violations(entries: list[dict]) -> list[dict]:
    """Return non-basic card names whose total quantity across enforced
    sections exceeds 1.

    Grouping is BY NAME (not card_id) so two printings of the same card still
    count as a duplicate. Basics are exempt. Maybeboard is excluded.
    """
    by_name: dict[str, list[dict]] = {}
    for e in entries:
        if e.get("section") not in ENFORCED_SECTIONS:
            continue
        if _is_basic_land(e):
            continue
        name = e.get("name") or ""
        by_name.setdefault(name, []).append(e)
    out: list[dict] = []
    for name, group in by_name.items():
        total_qty = sum(int(g.get("quantity") or 0) for g in group)
        if total_qty > 1:
            out.append({
                "name": name,
                "quantity": total_qty,
                "entry_ids": [g.get("id") for g in group],
            })
    # Stable ordering by name for deterministic output.
    out.sort(key=lambda v: v["name"].lower())
    return out


# ---------------------------------------------------------------------------
# Commander-section check
# ---------------------------------------------------------------------------


def _check_commanders(commanders: list[dict]) -> dict:
    """Validate the contents of the commander section.

    Returns ``{valid, count, reason, message, names, pairing}``.
    """
    n = len(commanders)

    if n == 0:
        return {
            "valid": False,
            "count": 0,
            "reason": "no_commander",
            "message": "No commander set.",
            "names": [],
            "pairing": None,
        }

    if n == 1:
        c = commanders[0]
        ok = can_be_commander(c) and int(c.get("quantity") or 1) == 1
        return {
            "valid": ok,
            "count": 1,
            "reason": None if ok else "ineligible_solo",
            "message": (
                ""
                if ok
                else f"{c.get('name', '?')} cannot be your commander."
            ),
            "names": [c.get("name")],
            "pairing": None,
        }

    if n == 2:
        a, b = commanders[0], commanders[1]
        # Each card must be commander-eligible OR carry a pairing keyword.
        a_eligible = can_be_commander(a) or _partner_kind(a) != "none"
        b_eligible = can_be_commander(b) or _partner_kind(b) != "none"
        pair_ok = commander_pair_legal(a, b)
        qty_ok = all(int(c.get("quantity") or 1) == 1 for c in commanders)
        ok = a_eligible and b_eligible and pair_ok and qty_ok

        reason = None
        msg = ""
        if not ok:
            if not pair_ok:
                reason = "incompatible_pair"
                msg = (
                    f"{a.get('name', '?')} and {b.get('name', '?')} "
                    "cannot be commanders together."
                )
            elif not (a_eligible and b_eligible):
                reason = "ineligible_pair"
                msg = "One or both cards cannot be your commander."
            else:
                reason = "qty"
                msg = "Each commander must have quantity 1."
        return {
            "valid": ok,
            "count": 2,
            "reason": reason,
            "message": msg,
            "names": [a.get("name"), b.get("name")],
            "pairing": _describe_pairing(a, b) if pair_ok else None,
        }

    return {
        "valid": False,
        "count": n,
        "reason": "too_many",
        "message": "At most two commanders are allowed.",
        "names": [c.get("name") for c in commanders],
        "pairing": None,
    }


# ---------------------------------------------------------------------------
# Top-level report
# ---------------------------------------------------------------------------


def deck_legality_report(deck: dict, entries: list[dict]) -> dict:
    """Compute a full legality report for a deck.

    For non-commander formats, returns a no-op ``{format, legal: True, checks: {}}``.
    """
    fmt = (deck.get("format") or "casual").lower()
    if fmt != "commander":
        return {"format": fmt, "legal": True, "checks": {}}

    entries = list(entries)
    commanders = [e for e in entries if e.get("section") == "commander"]
    main_total = sum(
        int(e.get("quantity") or 0)
        for e in entries
        if e.get("section") == "main"
    )
    commander_total = sum(int(c.get("quantity") or 0) for c in commanders)

    cmd_check = _check_commanders(commanders)

    # Only compute color-identity violations when the commander section itself
    # is valid — otherwise the "allowed" set is meaningless.
    allowed_ci = (
        commander_color_identity(commanders) if cmd_check["valid"] else []
    )
    ci_violations = color_identity_violations(allowed_ci, entries)
    singletons = singleton_violations(entries)

    target_size = 100
    actual_size = commander_total + main_total
    size_ok = actual_size == target_size

    legal = (
        cmd_check["valid"]
        and not ci_violations
        and not singletons
        and size_ok
    )

    return {
        "format": fmt,
        "legal": legal,
        "checks": {
            "commander": cmd_check,
            "color_identity": {
                "allowed": allowed_ci,
                "violations": ci_violations,
                "ok": not ci_violations,
            },
            "singleton": {
                "violations": singletons,
                "ok": not singletons,
            },
            "size": {
                "target": target_size,
                "actual": actual_size,
                "main": main_total,
                "commander": commander_total,
                "ok": size_ok,
            },
        },
    }
