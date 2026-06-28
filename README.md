# MTG Deck Builder — Interview Project

A self-contained web application for searching Magic: The Gathering cards and
organizing them into decks, built as a personal project to demonstrate
end-to-end product thinking: scoping, API integration, async backend design,
data modeling, and front-end UX.

> Built with FastAPI, SQLite, async HTTPX, Jinja2, and vanilla JS — no
> frameworks, no build step. Ships with a one-command Docker + Caddy
> deployment for HTTPS on a VPS.

---

## Presentation map

This README doubles as the talking-points document for a 5–10 minute
walkthrough. Each section maps to the interview brief.

| Brief item                          | Section below                      |
|-------------------------------------|------------------------------------|
| Objective                           | [Objective](#objective)            |
| Approach                            | [Approach](#approach)              |
| Tools                               | [Tools](#tools)                    |
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

I broke the project into six sub-problems and made a deliberate decision for
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

5. **How do I validate commander decks?**
   Commander format has strict rules: exactly 100 cards, singleton (no
   duplicates except basics), and every card's color identity must fit inside
   the commander's. I built a pure-function module (`app/commander.py`) that
   returns a structured legality report — no DB hits, no I/O — so the same
   logic powers the live `/api/decks/{id}/legality` endpoint and is trivially
   testable. The frontend surfaces violations in real time as cards are added
   or moved.

6. **How do I surface useful "add this" suggestions?**
   A hybrid recommendation engine (`app/recommend.py`): a curated colorless
   **staples** list for commander decks (Sol Ring, Arcane Signet, etc.),
   followed by up to 3 **theme categories** detected from the deck's combined
   oracle text — artifact synergy, tokens, graveyard, +1/+1 counters, lands
   matter, card draw, and more. Each theme fires a Scryfall search scoped to
   the deck's color identity, with cards already in the deck excluded.
   Results are cached in-memory keyed by `(deck_id, card_id_set)` so quantity
   changes are cache hits but add/remove invalidates.

## Tools

| Layer       | Choice                                | Why                                          |
|-------------|---------------------------------------|----------------------------------------------|
| Backend     | FastAPI + Uvicorn                     | Async-native, clean type hints, fast to scan |
| HTTP        | HTTPX                                 | First-class async, matches FastAPI's model   |
| Database    | SQLite via aiosqlite                  | Zero-ops persistence, async-friendly         |
| Validation  | Pydantic                              | Request/response schemas for free            |
| Templates   | Jinja2                                | Server-rendered, no SPA complexity           |
| Frontend    | Vanilla JS, SortableJS, Chart.js, Mana font | No build step, loads from CDN           |
| Deployment  | Docker Compose + Caddy 2              | One-command rebuild, automatic HTTPS         |

The deliberate constraint was **no front-end framework and no build step**.
For a single-page tool with three sections, a SPA would have added complexity
without buying anything. The result is a project anyone can clone, `pip
install`, and run locally — or push to a VPS as a one-shot Docker Compose
stack.

## Outcome

A working app that delivers every feature from the original brief plus two
additions that rounded it out into something I'd actually use:

- Card search with Scryfall's full query syntax and type-ahead autocomplete.
- One-click Basic Lands toolbar for the five canonical basics.
- Three drag-and-drop deck sections with quantity controls.
- Live mana-curve bar chart and color-distribution doughnut, refreshed on
  every change.
- Card preview panel with image, mana symbols (rendered with the Mana font),
  type line, oracle text, and a Front/Back toggle for double-faced cards.
- **Commander format enforcement**: live legality check (100 cards,
  singleton, color identity) surfaced in the editor as cards are added.
- **Deck-aware recommendations**: curated commander staples plus theme-matched
  cards detected from the deck's contents, refreshed automatically after
  every add or remove.
- Export to plain text, MTGO (`.dek`), and CSV.
- Persistent storage in a single `magic.db` file — no login, no account.

I verified the whole flow end-to-end against the live Scryfall API:
searching "Lightning Bolt", adding 4× to the main deck, dragging entries
across sections, exporting all three formats, and confirming both the stats
and the legality report recalculated correctly.

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

### 4. The Scryfall staples query syntax was invalid

The first cut of the recommendation engine tried to fetch commander staples
in a single bulk Scryfall search using the `!"Name"` exact-name operator
chained with `OR`: `(!"Sol Ring" OR !"Arcane Signet" OR ...)`. The search
endpoint rejected it — the `!` exact-name operator is unreliable inside
multi-clause `/cards/search` queries.

**Fix**: Switched to per-card `get_card_by_name` lookups (which hit the
DB-cached `/cards/named` path) fired concurrently via `asyncio.gather`. The
client's 150 ms rate limiter serializes the actual HTTP, but the code stays
linear and the second-run cost is effectively zero because every name is
already in the SQLite cache.

**Lesson**: When a third-party search API offers a "convenient" bulk syntax,
verify it on a real query before building on it. The two-endpoint split
(`search` vs `named`) exists for a reason — exact lookups belong on the
named endpoint.

## What I learned

- **Async end-to-end**: thinking deliberately about where concurrency helps
  (Scryfall client, parallel recommendation searches) and where it doesn't
  (single-user SQLite). The `asyncio.Lock` + monotonic-clock throttle
  pattern is reusable.
- **Reading upstream contracts carefully**: the Starlette, aiosqlite, and
  Scryfall bugs all reduced to "I assumed the API; I should have inspected
  it."
- **Modeling irregular real-world data**: handling multi-faced cards without
  a separate table — falling back to `card_faces[0]` for top-level fields
  while preserving the full faces array for the UI's Front/Back toggle.
- **Pure-function domains for complex rules**: commander legality and theme
  detection are both implemented as pure functions taking data in, returning
  data out. No I/O, no globals — easy to test, easy to reason about, and the
  endpoints around them stay thin.
- **Designing for failure**: atomic transactions for the drag-and-drop move
  endpoint, with rollback + a client-side reload fallback if the network
  call fails mid-drag.
- **Knowing when not to abstract**: this is a single-user local tool, so I
  resisted adding an ORM, a service layer, or a SPA framework — the simplest
  thing that works.

## Quick start

Two paths: **local dev** for working on the code, **Docker** for a real
deployment.

### Option A — Local development

```bash
git clone https://github.com/stalker-doge/Magic-Deck-Builder.git
cd Magic-Deck-Builder
python -m venv .venv
.venv\Scripts\activate         # Windows
pip install -r requirements.txt
python run.py
# open http://127.0.0.1:8000
```

Requires Python 3.10+ (developed and tested on 3.14; the Docker image pins
3.12-slim for stable prebuilt wheels).

### Option B — Production deployment (Docker + Caddy + HTTPS)

The repo ships with a `Dockerfile`, `docker-compose.yml`, and `Caddyfile`
that bundle the app behind [Caddy 2](https://caddyserver.com/), which
provisions and renews a Let's Encrypt certificate automatically on first
boot.

Prerequisites: a VPS with a public IP, Docker Engine + Compose plugin
installed, and a DNS A record for your domain already pointing at the VPS.

```bash
git clone https://github.com/stalker-doge/Magic-Deck-Builder.git
cd Magic-Deck-Builder
cp .env.example .env
nano .env                       # set DOMAIN and ACME_EMAIL
docker compose up -d --build
docker compose logs -f caddy    # wait for "certificate obtained successfully"
curl -I https://YOUR_DOMAIN/    # expect HTTP/2 200
```

Caddy handles HTTP→HTTPS redirect, TLS provisioning, and HTTP/2 / HTTP/3
transparently. The SQLite database lives in a named Docker volume
(`magic-db`) so it survives `docker compose down` and image rebuilds.

**Update later** with:

```bash
git pull && docker compose up -d --build
```

**Back up the database** with:

```bash
docker compose cp app:/data/magic.db ~/backups/magic-$(date +%Y%m%d-%H%M%S).db
```

> The single uvicorn worker is **required** — the app uses a module-level
> singleton aiosqlite connection and an in-memory recommendation cache, so
> multiple workers would diverge. Don't raise `--workers` without refactoring
> those first.

---

## Appendix — project structure

```
app/
├── main.py              FastAPI app, lifespan, router mounts
├── config.py            Paths, Scryfall URL, rate limit, cache TTLs (env-aware)
├── database.py          SQLite schema + async query helpers
├── models.py            Pydantic request/response schemas
├── scryfall.py          Async Scryfall client (throttle, retry, cache, normalize)
├── stats.py             Mana curve + color distribution (pure functions)
├── export.py            Text/MTGO/CSV serializers (pure functions)
├── commander.py         Commander legality rules (pure functions)
├── recommend.py         Hybrid staples + theme recommendation engine
└── routers/
    ├── pages.py         HTML page routes
    ├── decks.py         Deck + entry + legality + recs JSON APIs
    ├── cards.py         Search/autocomplete/basics/get-card JSON APIs
    └── export.py        Export download endpoints
templates/               Jinja2 (base, index, deck_form, deck_editor, error)
static/
├── css/style.css
└── js/
    ├── app.js           Main editor: search, drag-drop, stats refresh
    ├── preview.js       Card preview panel + Front/Back toggle
    ├── stats.js         Chart.js mana curve + color doughnut
    ├── legality.js      Live commander legality panel
    └── recommend.js     Recommendations panel + refresh hooks
requirements.txt
run.py                   Local dev entrypoint (reload on 127.0.0.1:8000)
Dockerfile               Production image (uvicorn, single worker, proxy headers)
docker-compose.yml       app + caddy services, named volumes for db + certs
Caddyfile                {$DOMAIN} → reverse_proxy app:8000 (auto-HTTPS)
.env.example             DOMAIN and ACME_EMAIL placeholders
.dockerignore
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
| GET    | `/cards/basics`                   | The five basic lands for the toolbar     |
| GET    | `/cards/{card_id}`                | Cache-first single card lookup           |
| POST   | `/decks/{id}/cards`               | Add card to a section                    |
| PATCH  | `/decks/{id}/entries/{entry_id}`  | Update quantity and/or section           |
| DELETE | `/decks/{id}/entries/{entry_id}`  | Remove entry                             |
| POST   | `/decks/{id}/move`                | Drag-and-drop move + reorder (atomic)    |
| GET    | `/decks/{id}/entries`             | All entries with joined card data        |
| GET    | `/decks/{id}/stats`               | Mana curve + colors + section totals     |
| GET    | `/decks/{id}/legality`            | Commander legality report                |
| GET    | `/decks/{id}/recommendations`     | Staples + theme-matched suggestions      |

## Credit

Card data, images, and search are provided by [Scryfall](https://scryfall.com).
This project is unaffiliated with Scryfall or Wizards of the Coast and is for
personal deck-building use only.
