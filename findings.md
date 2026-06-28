# Findings & Decisions

## Requirements
- Improve the front-end design of the MTG Deck Builder project at C:\Projects\Magic
- Make it visually more fitting for Magic: The Gathering
- Use the planning-with-files skill and the frontend-design skill
- (Implicit) Preserve all existing functionality — this is a visual redesign, not a rebuild

## Research Findings

### Project Identity
- **App:** MTG Deck Builder (personal/interview project)
- **Stack:** FastAPI + Jinja2 + SQLite (async); vanilla JS front-end; no build step
- **Purpose:** Search Scryfall, build decks (main/sideboard/maybe), live stats, export TXT/MTMO/CSV

### Front-End Touchpoints (complete inventory)

**Templates (Jinja2):**
1. `templates/base.html` — topbar (brand "✦" + nav + New Deck btn), container, footer (Scryfall attribution); CDN: Mana font 1.16.0, SortableJS 1.15.6, Chart.js 4.4.7
2. `templates/index.html` — deck list; `.deck-grid` with deck cards (name, format badge, counts, delete)
3. `templates/deck_form.html` — name / format select / description
4. `templates/deck_editor.html` — 3-column workspace: search | deck sections (main/sb/maybe) | stats+preview
5. `templates/error.html` — status code + message + back button

**CSS:** single file `static/css/style.css` (~576 lines). Dark theme + MTG gold accent + mana color vars. CSS Grid editor layout (320px | 1fr | 280px), collapses <1100px.

**JS:**
- `static/js/app.js` (444 lines) — editor orchestration, drag-drop, search, autocomplete
- `static/js/preview.js` (156 lines) — mana cost parsing, card preview, DFC toggle
- `static/js/stats.js` (126 lines) — Chart.js mana-curve bar + color doughnut

**No local images/fonts.** Card images come from Scryfall CDN.

### Current Design System
| Token | Value |
|-------|-------|
| `--bg` | `#0f1419` (deep navy/black) |
| `--bg-elev` / `--bg-elev-2` | `#1a2128` / `#232c36` |
| `--accent` (MTG gold) | `#d4a857` |
| `--primary` (blue) | `#4a90c2` |
| `--danger` (red) | `#c2554e` |
| Mana colors W/U/B/R/G/C | `#f8f4e8 / #4a90c2 / #5a4f6b / #c2554e / #5a8f4a / #a8a8a8` |
| Font | System stack, 14px base |
| Container | max-width 1600px |

### Strengths to Preserve
- Solid design-token foundation (CSS vars already in place)
- Mana font already integrated and working
- Clean 3-column editor layout
- Functional, verified end-to-end

### Weaknesses to Address
- Generic dark mode — no overt fantasy/arcane motif
- No display/typeface hierarchy (system fonts only)
- No texture or depth (flat backgrounds)
- Deck cards look like generic UI cards, not MTG cards
- Topbar brand is a single "✦" glyph — underwhelming
- No rarity/color storytelling despite MTG theme
- Charts are Chart.js defaults, not themed to MTG

## Visual/Browser Findings
- (Will capture MTG visual reference notes here during Phase 2)

## Resources
- Mana font CDN already wired in base.html
- Scryfall CDN provides card images at runtime
- Chart.js theming via options objects in stats.js
- Reference: MTG card back is iconic (blue lacquer + gold ornamental ring + red center gem)

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Front-end-only scope | User asked specifically for design improvement |
| Refactor in place (same files) | Avoids breaking Jinja template references |
| Layer theming on existing tokens | Preserve what works; enhance what doesn't |
| Use frontend-design skill for Phase 3-5 implementation | User explicitly requested it |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| (none yet) |  |

---
*Update this file after every 2 view/browser/search operations*
