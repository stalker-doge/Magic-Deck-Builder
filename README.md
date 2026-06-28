# MTG Deck Builder — Interview Project

A self-contained web application for searching Magic: The Gathering cards and
organizing them into decks, built as a personal project to demonstrate
end-to-end product thinking: scoping, API integration, async backend design,
data modeling, and front-end UX.

> Built with FastAPI, SQLite, async HTTPX, Jinja2, and vanilla JS — no
> frameworks, no build step.

---

## Presentation map

This README doubles as the talking-points document for a 5–10 minute
walkthrough. Each section maps to the interview brief.

| Brief item                          | Section below                      |
|-------------------------------------|------------------------------------|
| Objective                           | [Objective](#objective)            |
| Approach                             | [Approach](#approach)              |
| Tools used                          | [Tools](#tools)                    |
| Outcome                             | [Outcome](#outcome)                |
| Challenges & how I overcame them    | [Challenges](#challenges--fixes)   |
| What I learned                      | [Learnings](#what-i-learned)       |
| Run it yourself                     | [Quick start](#quick-start)        |

---

## Objective

> Build a small but complete web app that lets a Magic: The Gathering player
> look up cards and organize them into decks — quickly, locally, and without
> needing an account.

I wanted a project that would let me practice the full lifecycle of a small
product in a realistic, constraint-heavy setting (a public rate-limited API,
multi-shaped data, drag-and-drop UX) rather than a contrived tutorial.
Magic has rich, irregular data — double-faced cards, hybrid mana, multi-color
identities — which made it a good test of how cleanly I could model and
render something that doesn't fit tidy rows.

## Approach

I broke the project into four sub-problems and made a deliberate decision for
each:

1. **Where do cards come from?**
   Use the public [Scryfall API](https://scryfall.com/docs/api) as the single
   source of truth. No bulk data download — search on demand, cache the
   individual cards that come back so future lookups are local.

2. **How do I avoid hammering Scryfall?**
   Scryfall asks for 50–100 ms between requests and enforces 10 req/s. I built
   an async client with a 150 ms throttle (single lock, monotonic clock),
   exponential backoff on HTTP 429, and a tiered cache:
   - **30-day SQLite cache** for individual cards.
   - **5-minute in-memory cache** for autocomplete (called on every keystroke).
   - **No server-side image fetching** — image URLs point at Scryfall's CDN,
     which is not rate-limited, so the browser loads them directly.

3. **How should a deck be modeled?**
   Three tables: `decks`, `cards` (denormalized cache), and a join table
   `deck_card_entries` with `section` (`main`/`sideboard`/`maybe`), `quantity`,
   and `sort_order`. The unique constraint `(deck_id, card_id, section)` means
   "add the same card again" naturally becomes "increment quantity" rather
   than a duplicate row.

4. **How do I make drag-and-drop between sections feel solid?**
   Use SortableJS with a shared `group` so cards can be dragged across Main /
   Sideboard / Maybeboard. On drop, the frontend sends the entry id, source
   and destination sections, and the **new ordered id arrays** for both. The
   backend re-applies ordering in a single transaction — atomic and reversible
   on failure.

## Tools

| Layer      | Choice                                | Why                                          |
|------------|---------------------------------------|----------------------------------------------|
| Backend    | FastAPI + Uvicorn                     | Async-native, clean type hints, fast to scan |
| HTTP       | HTTPX                                 | First-class async, matches FastAPI's model   |
| Database   | SQLite via aiosqlite                  | Zero-ops persistence, async-friendly         |
| Validation | Pydantic                              | Request/response schemas for free            |
| Templates  | Jinja2                                | Server-rendered, no SPA complexity           |
| Frontend   | Vanilla JS, SortableJS, Chart.js, Mana font | No build step, loads from CDN           |

The deliberate constraint was **no front-end framework and no build step**.
For a single-page tool with three sections, a SPA would have added complexity
without buying anything. The result is a project anyone can clone, `pip
install`, and run.

## Outcome

A working local app that delivers every feature from the original brief:

- Card search with Scryfall's full query syntax and type-ahead autocomplete.
- Three drag-and-drop deck sections with quantity controls.
- Live mana-curve bar chart and color-distribution doughnut, refreshed on
  every change.
- Card preview panel with image, mana symbols (rendered with the Mana font),
  type line, oracle text, and a Front/Back toggle for double-faced cards.
- Export to plain text, MTGO (`.dek`), and CSV.
- Persistent storage in a single `magic.db` file — no login, no account.

I verified the whole flow end-to-end against the live Scryfall API:
searching "Lightning Bolt", adding 4× to the main deck, dragging entries
across sections, exporting all three formats, and confirming the stats
recalculated correctly.

## Challenges & fixes

This section is the most honest part of the project. Each bug below was a
real failure I hit during verification, diagnosed, and fixed.

### 1. Pinned dependencies broke on Python 3.14

I started with exact version pins (e.g. `pydantic==2.10.4`). On my dev
machine (Python 3.14) `pip install` failed trying to compile `pydantic-core`
from source — there was no pre-built wheel for that combination.

**Fix**: Switched the pins to `>=` ranges and let pip pick versions that
ship Python 3.14 wheels (e.g. `pydantic 2.13.4` with `pydantic-core 2.46.4`).
**Lesson**: Don't over-pin libraries with native extensions unless you also
control the runtime.

### 2. Starlette's `TemplateResponse` signature changed

My page routes returned 500 errors with `TypeError: cannot use 'tuple' as a
dict key (unhashable type: 'dict')` deep inside Jinja2's template cache. I
chased the wrong trail briefly (suspected Jinja2 internals) before realizing
newer Starlette requires the `Request` object as the **first** positional
argument:

```python
# Old API (broken on Starlette 1.x)
templates.TemplateResponse("index.html", {"request": request, ...})

# New API
templates.TemplateResponse(request, "index.html", {...})
```

**Lesson**: When a stack trace dives into a library, the bug is usually in
how you're calling the library — read the installed signature, don't trust
the docs you remember.

### 3. My database helper broke named-parameter queries

The trickiest bug. Cards weren't being cached even though search returned
results — meaning every "add to deck" failed with `FOREIGN KEY constraint
failed` (the card_id didn't exist in `cards`).

Root cause: my generic `execute()` helper wrapped params in `tuple(params)`,
which is correct for `?` placeholders but **silently corrupted dict params**
for `:name` placeholders. The error was swallowed by a defensive
`try/except` in the Scryfall client, so the symptom was invisible.

**Fix**: Removed the `tuple()` coercion so the helper accepts either a
sequence (for `?`) or a dict (for `:name`):

```python
async def execute(sql, params=()):
    cur = await db.execute(sql, params)  # let sqlite3 bind correctly
    await db.commit()
    return cur
```

I also replaced the silent `except Exception: pass` with a logged warning so
this class of bug surfaces immediately in future.

**Lesson**: Defensive `try/except: pass` is a footgun. If you must swallow
errors, log them — and prefer fixing the call-site contract over hiding the
failure.

## What I learned

- **Async end-to-end**: thinking deliberately about where concurrency helps
  (Scryfall client) and where it doesn't (single-user SQLite). The
  `asyncio.Lock` + monotonic-clock throttle pattern is reusable.
- **Reading upstream contracts carefully**: the Starlette and aiosqlite bugs
  both reduced to "I assumed the API; I should have inspected it."
- **Modeling irregular real-world data**: handling multi-faced cards without
  a separate table — falling back to `card_faces[0]` for top-level fields
  while preserving the full faces array for the UI's Front/Back toggle.
- **Designing for failure**: atomic transactions for the drag-and-drop move
  endpoint, with rollback + a client-side reload fallback if the network
  call fails mid-drag.
- **Knowing when not to abstract**: this is a single-user local tool, so I
  resisted adding an ORM, a service layer, or a SPA framework — the simplest
  thing that works.

## Quick start

```bash
cd C:\Projects\Magic
pip install -r requirements.txt
python run.py
# open http://127.0.0.1:8000
```

Requires Python 3.10+ (developed and tested on 3.14).

---

## Appendix — project structure

```
app/
├── main.py              FastAPI app, lifespan, router mounts
├── config.py            Paths, Scryfall URL, rate limit, cache TTLs
├── database.py          SQLite schema + async query helpers
├── models.py            Pydantic request/response schemas
├── scryfall.py          Async Scryfall client (throttle, retry, cache, normalize)
├── stats.py             Mana curve + color distribution (pure functions)
├── export.py            Text/MTGO/CSV serializers (pure functions)
└── routers/
    ├── pages.py         HTML page routes
    ├── decks.py         Deck + entry JSON APIs (incl. /move for drag-drop)
    ├── cards.py         Search/autocomplete/get-card JSON APIs
    └── export.py        Export download endpoints
templates/               Jinja2 (base, index, deck_form, deck_editor, error)
static/                  CSS + vanilla JS (app.js, preview.js, stats.js)
requirements.txt
run.py
```

## Appendix — HTTP API

**HTML pages**

| Method | Path                       | Purpose                    |
|--------|----------------------------|----------------------------|
| GET    | `/`                        | Deck list                  |
| GET    | `/decks/new`               | New deck form              |
| POST   | `/decks`                   | Create deck, redirect      |
| GET    | `/decks/{id}`              | Deck editor workspace      |
| POST   | `/decks/{id}/delete`       | Delete deck                |
| GET    | `/decks/{id}/export/{fmt}` | Download `txt`/`mtgo`/`csv`|

**JSON API** (mounted under `/api`)

| Method | Path                              | Purpose                                  |
|--------|-----------------------------------|------------------------------------------|
| GET    | `/cards/search?q=&page=`          | Scryfall search, caches returned cards   |
| GET    | `/cards/autocomplete?q=`          | Type-ahead name list (5-min in-mem cache)|
| GET    | `/cards/{card_id}`                | Cache-first single card lookup           |
| POST   | `/decks/{id}/cards`               | Add card to a section                    |
| PATCH  | `/decks/{id}/entries/{entry_id}`  | Update quantity and/or section           |
| DELETE | `/decks/{id}/entries/{entry_id}`  | Remove entry                             |
| POST   | `/decks/{id}/move`                | Drag-and-drop move + reorder (atomic)    |
| GET    | `/decks/{id}/entries`             | All entries with joined card data        |
| GET    | `/decks/{id}/stats`               | Mana curve + colors + section totals     |

## Credit

Card data, images, and search are provided by [Scryfall](https://scryfall.com).
This project is unaffiliated with Scryfall or Wizards of the Coast and is for
personal deck-building use only.
