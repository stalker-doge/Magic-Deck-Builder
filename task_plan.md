# Task Plan: MTG Deck Builder — Front-End Visual Redesign

## Goal
Transform the MTG Deck Builder's front-end from a clean-but-generic dark mode into an immersive, Magic: The Gathering-themed experience — evoking the look and feel of premium card frames, arcane parchment, mana energies, and the iconic MTG card back, while preserving all existing functionality and the no-build-step vanilla JS architecture.

## Current Phase
All phases complete (1–6)

## Phases

### Phase 1: Requirements & Discovery
- [x] Understand user intent: "improve front-end design, make it more fitting for Magic: The Gathering visually"
- [x] Map every front-end touchpoint (templates, CSS, JS, assets)
- [x] Identify constraints: vanilla JS, no build step, CDN deps (Mana font, SortableJS, Chart.js), FastAPI + Jinja2 backend untouched
- [x] Document current design system in findings.md
- **Status:** complete

### Phase 2: Design System & Direction
- [x] Define the MTG visual language (typography, palette, textures, motifs)
- [x] Choose decorative assets (card-back pattern, parchment, mana orbs, set symbols)
- [x] Decide on font(s) for display vs. body
- [x] Document the new design tokens (CSS custom properties)
- [x] Confirm direction with user before implementation
- **Status:** complete

### Phase 3: Base Layer & Global Theme
- [x] Rewrite design tokens in style.css (palette, fonts, radii, shadows, glows)
- [x] Add background texture (subtle MTG card-back / arcane pattern)
- [x] Restyle topbar with ornamental gold brand mark + MTG wordmark feel
- [x] Restyle buttons, inputs, dropdowns, badges in MTG frame style
- [x] Add display + body font loading (Google Fonts: Cinzel + Hanken Grotesk)
- **Status:** complete

### Phase 4: Page-Level Redesigns
- [x] **index.html** — deck cards styled like MTG premium cards (gold top bar, inner hairline frame, hover lift, staggered fade-in); added mana-pie hero (WUBRG pip emblem)
- [x] **deck_form.html** — themed via CSS (parchment-accented form panel, gold top accent, Cinzel labels)
- [x] **deck_editor.html** — themed 3-column workspace via CSS (◆-prefixed panel titles, engraved section counts, gold-bordered preview)
- [x] **error.html** — themed via CSS (diamond ornaments, gold status code)
- **Status:** complete

### Phase 5: Interactive Polish
- [x] Enhanced Chart.js themes (metallic gold mana-curve gradient, W/U/B/R/G/C doughnut with hoverOffset, themed tooltips)
- [x] Hover/transition micro-animations (deck-card lift + gold glow, draggable entry gold accent trail, dropdown slide-in)
- [x] Restyle mana symbol rendering (orb backgrounds with radial highlight + gold ring)
- [x] Mana-pie hero with per-color glow + staggered pulse animation
- [x] Reduced-motion media query for accessibility
- **Status:** complete

### Phase 6: Verification & Delivery
- [x] CSS braces balanced (203/203)
- [x] All Jinja template tags balanced across 5 templates
- [x] Python files syntactically valid & unchanged
- [x] FastAPI app imports cleanly; all 5 page routes + 9 API/export routes intact
- [x] Cross-checked every JS-referenced class/ID has matching CSS rule
- [x] Responsive breakpoint preserved (1180px collapse)
- [x] Summarized changes for user
- **Status:** complete

## Key Questions
1. ~~How "loud" should the MTG theming be?~~ → **ANSWERED: Premium arcane** (dark mystical, gold ornamental borders, subtle card-back texture, fantasy display serif, mana-pip accents, rarity-glow on hover)
2. ~~Add custom display font?~~ → **ANSWERED: Yes** (Cinzel for display/headings; body stays clean sans-serif)
3. Keep dark theme as primary? → Yes; dark base with parchment/gold accents
4. Sound effects? → No (visual only)

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Preserve vanilla JS / no build step | User constraint; existing architecture is solid |
| Keep FastAPI/Jinja2 backend untouched | Task is front-end only |
| Keep CDN deps (Mana font, SortableJS, Chart.js) | Already integrated; replacing adds risk |
| Single style.css refactor (not CSS modules) | Matches current architecture |
| Use Google Fonts for display typeface | No build step, reliable CDN |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| Mana symbols rendered empty EVERYWHERE (pie, deck entries, search, preview) | 3 | **Real root cause:** `base.html` referenced `@mana-fonts/mana@1.16.0` which 404s on jsDelivr — the scoped package doesn't exist. Correct package is unscoped `mana-font`. Fix: changed CDN URL to `mana-font@1.15.9` (verified HTTP 200, 45KB CSS with valid `.ms`/`@font-face`/`::before` rules). My earlier CSS-only "fixes" were treating symptoms, not cause — I should have verified the font was loading first. |
| Mana curve canvas grew unboundedly in deck editor | 1 | Chart.js v4 `responsive:true` + `maintainAspectRatio:false` inside a scrolling flex parent caused ResizeObserver feedback. Fix: wrapped each canvas in a fixed-height (180px) `position:relative` `.chart-wrap` and absolutely-positioned the canvas — the canonical Chart.js responsive pattern. |

## Notes
- Re-read this plan before each phase transition.
- Front-end-only: do not modify app/, models, or routers.
- All visual changes go in templates/, static/css/, static/js/.
