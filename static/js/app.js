// app.js — Main editor orchestration: search, autocomplete, add cards,
// deck section rendering, drag-and-drop between sections.

(function () {
    "use strict";

    const DECK_ID = window.DECK_ID;
    const SECTIONS = ["main", "sideboard", "maybe"];
    const SECTION_LABELS = { main: "Main Deck", sideboard: "Sideboard", maybe: "Maybeboard" };

    // In-memory state: entries keyed by id, plus per-section ordered arrays.
    const state = {
        entries: new Map(),       // entry_id -> entry object
        sectionOrder: { main: [], sideboard: [], maybe: [] }, // entry_ids per section
    };

    // ---------------------------------------------------------------------
    // Helpers
    // ---------------------------------------------------------------------

    function escapeHtml(s) {
        if (s == null) return "";
        return String(s).replace(/[&<>"']/g, ch => ({
            "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
        }[ch]));
    }

    async function api(url, options = {}) {
        const resp = await fetch(url, {
            headers: { "Content-Type": "application/json" },
            ...options,
        });
        if (!resp.ok) {
            let detail = `${resp.status}`;
            try { detail = (await resp.json()).detail || detail; } catch (_) { /* ignore */ }
            throw new Error(detail);
        }
        // Some endpoints return no body.
        const ct = resp.headers.get("content-type") || "";
        if (ct.includes("application/json")) return resp.json();
        return null;
    }

    function debounce(fn, ms) {
        let timer;
        return function (...args) {
            clearTimeout(timer);
            timer = setTimeout(() => fn.apply(this, args), ms);
        };
    }

    function truncate(s, n) {
        if (!s) return "";
        return s.length > n ? s.slice(0, n - 1) + "…" : s;
    }

    // ---------------------------------------------------------------------
    // Section rendering
    // ---------------------------------------------------------------------

    function renderAllSections() {
        SECTIONS.forEach(renderSection);
    }

    function renderSection(section) {
        const ul = document.getElementById(`section-${section}`);
        if (!ul) return;
        const ids = state.sectionOrder[section];
        const countEl = document.querySelector(`[data-count-target="${section}"]`);

        const total = ids.reduce((sum, id) => sum + (state.entries.get(id)?.quantity || 0), 0);
        if (countEl) countEl.textContent = total;

        if (!ids.length) {
            ul.innerHTML = `<li class="deck-empty-hint">No cards here. Drag cards in or add from search.</li>`;
            return;
        }

        ul.innerHTML = ids.map(id => renderEntry(state.entries.get(id))).join("");

        // Wire per-entry handlers.
        ul.querySelectorAll(".deck-entry").forEach(li => {
            const id = parseInt(li.dataset.entryId, 10);
            li.addEventListener("mouseenter", () => {
                const entry = state.entries.get(id);
                if (entry) window.schedulePreview(entry, li);
            });
            li.addEventListener("mouseleave", () => window.cancelPreview());
            li.addEventListener("click", (e) => {
                if (e.target.closest("button")) return; // ignore button clicks
                const entry = state.entries.get(id);
                if (entry) window.renderPreview(entry, li);
            });

            const decBtn = li.querySelector(".qty-dec");
            const incBtn = li.querySelector(".qty-inc");
            const rmBtn = li.querySelector(".remove");
            if (decBtn) decBtn.addEventListener("click", () => changeQuantity(id, -1));
            if (incBtn) incBtn.addEventListener("click", () => changeQuantity(id, 1));
            if (rmBtn) rmBtn.addEventListener("click", () => removeEntry(id));
        });
    }

    function renderEntry(entry) {
        if (!entry) return "";
        const manaHtml = window.renderMana(entry.mana_cost || "");
        return `
            <li class="deck-entry" data-entry-id="${entry.id}" data-card-id="${entry.card_id}">
                <span class="entry-qty">${entry.quantity}</span>
                <span class="entry-mana">${manaHtml}</span>
                <span class="entry-name" title="${escapeHtml(entry.name)}">${escapeHtml(entry.name)}</span>
                <span class="entry-type">${escapeHtml(truncate(entry.type_line, 30))}</span>
                <span class="entry-controls">
                    <button class="qty-dec" title="Decrease">−</button>
                    <button class="qty-inc" title="Increase">+</button>
                    <button class="remove" title="Remove">✕</button>
                </span>
            </li>
        `;
    }

    // ---------------------------------------------------------------------
    // Entry mutations
    // ---------------------------------------------------------------------

    async function addCard(cardId, section, quantity = 1) {
        try {
            await api(`/api/decks/${DECK_ID}/cards`, {
                method: "POST",
                body: JSON.stringify({ card_id: cardId, section, quantity }),
            });
            await reloadEntries();
            window.refreshStats();
        } catch (err) {
            alert(`Failed to add card: ${err.message}`);
        }
    }

    async function changeQuantity(entryId, delta) {
        const entry = state.entries.get(entryId);
        if (!entry) return;
        const newQty = entry.quantity + delta;
        if (newQty < 1) {
            return removeEntry(entryId);
        }
        try {
            await api(`/api/decks/${DECK_ID}/entries/${entryId}`, {
                method: "PATCH",
                body: JSON.stringify({ quantity: newQty }),
            });
            entry.quantity = newQty;
            renderSection(entry.section);
            window.refreshStats();
        } catch (err) {
            alert(`Failed to update quantity: ${err.message}`);
        }
    }

    async function removeEntry(entryId) {
        const entry = state.entries.get(entryId);
        if (!entry) return;
        try {
            await api(`/api/decks/${DECK_ID}/entries/${entryId}`, { method: "DELETE" });
            state.entries.delete(entryId);
            state.sectionOrder[entry.section] = state.sectionOrder[entry.section]
                .filter(id => id !== entryId);
            renderSection(entry.section);
            window.refreshStats();
        } catch (err) {
            alert(`Failed to remove card: ${err.message}`);
        }
    }

    // ---------------------------------------------------------------------
    // Reload all entries from server
    // ---------------------------------------------------------------------

    async function reloadEntries() {
        try {
            const data = await api(`/api/decks/${DECK_ID}/entries`);
            ingestEntries(data.entries || []);
            renderAllSections();
            window.refreshStats();
        } catch (err) {
            console.error("Failed to reload entries:", err);
        }
    }

    function ingestEntries(entries) {
        state.entries.clear();
        state.sectionOrder = { main: [], sideboard: [], maybe: [] };
        // Sort by sort_order within section.
        const bySection = { main: [], sideboard: [], maybe: [] };
        for (const e of entries) {
            state.entries.set(e.id, e);
            bySection[e.section]?.push(e);
        }
        for (const section of SECTIONS) {
            bySection[section].sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0));
            state.sectionOrder[section] = bySection[section].map(e => e.id);
        }
    }

    // ---------------------------------------------------------------------
    // Drag-and-drop via SortableJS
    // ---------------------------------------------------------------------

    function initSortable() {
        SECTIONS.forEach(section => {
            const el = document.getElementById(`section-${section}`);
            if (!el || typeof Sortable === "undefined") return;
            Sortable.create(el, {
                group: "deck-sections",
                animation: 150,
                handle: ".deck-entry",
                draggable: ".deck-entry",
                ghostClass: "dragging",
                filter: ".deck-empty-hint",
                preventOnFilter: false,
                onStart: () => window.hidePreview && window.hidePreview(),
                onEnd: handleDragEnd,
            });
        });
    }

    async function handleDragEnd(evt) {
        const entryId = parseInt(evt.item.dataset.entryId, 10);
        const fromSection = evt.from.dataset.section;
        const toSection = evt.to.dataset.section;
        const entry = state.entries.get(entryId);

        if (!entry) return;

        // Build new order arrays from the DOM.
        const newOrderFrom = collectOrder(evt.from);
        const newOrderTo = collectOrder(evt.to);

        try {
            await api(`/api/decks/${DECK_ID}/move`, {
                method: "POST",
                body: JSON.stringify({
                    entry_id: entryId,
                    from_section: fromSection,
                    to_section: toSection,
                    new_order_from: newOrderFrom,
                    new_order_to: newOrderTo,
                }),
            });

            // Update local state from DOM.
            entry.section = toSection;
            state.sectionOrder[fromSection] = newOrderFrom;
            if (fromSection !== toSection) {
                state.sectionOrder[toSection] = newOrderTo;
            }
            // Re-render counts/headers.
            renderSection(fromSection);
            if (fromSection !== toSection) renderSection(toSection);
            window.refreshStats();
        } catch (err) {
            alert(`Move failed: ${err.message}`);
            await reloadEntries();
        }
    }

    function collectOrder(ulElement) {
        return Array.from(ulElement.querySelectorAll(".deck-entry"))
            .map(li => parseInt(li.dataset.entryId, 10))
            .filter(n => !isNaN(n));
    }

    // ---------------------------------------------------------------------
    // Search + autocomplete
    // ---------------------------------------------------------------------

    function initSearch() {
        const input = document.getElementById("search-input");
        const acList = document.getElementById("autocomplete-list");
        const results = document.getElementById("search-results");
        const info = document.getElementById("search-info");

        if (!input) return;

        let lastAcQuery = "";
        let acActiveIndex = -1;

        // Autocomplete on input (debounced).
        const debouncedAutocomplete = debounce(async () => {
            const q = input.value.trim();
            if (q.length < 2) {
                acList.hidden = true;
                return;
            }
            try {
                const data = await api(`/api/cards/autocomplete?q=${encodeURIComponent(q)}`);
                const names = data.names || [];
                if (!names.length || q !== lastAcQuery) {
                    acList.hidden = true;
                    return;
                }
                acList.innerHTML = names.slice(0, 8)
                    .map(n => `<div class="ac-item" data-name="${escapeHtml(n)}">${escapeHtml(n)}</div>`)
                    .join("");
                acList.hidden = false;
                acActiveIndex = -1;
                acList.querySelectorAll(".ac-item").forEach(el => {
                    el.addEventListener("mousedown", (e) => {
                        e.preventDefault();
                        input.value = el.dataset.name;
                        acList.hidden = true;
                        doSearch();
                    });
                });
            } catch (_) {
                acList.hidden = true;
            }
            lastAcQuery = q;
        }, 200);

        // Full search on Enter.
        const doSearch = async () => {
            const q = input.value.trim();
            acList.hidden = true;
            if (!q) {
                results.innerHTML = "";
                info.hidden = true;
                return;
            }
            results.innerHTML = `<div class="search-empty">Searching…</div>`;
            info.hidden = false;
            info.textContent = `Searching for "${q}"…`;
            try {
                const data = await api(`/api/cards/search?q=${encodeURIComponent(q)}`);
                renderSearchResults(data.cards || [], data.total_cards || 0, q);
            } catch (err) {
                results.innerHTML = `<div class="search-empty">Search failed: ${escapeHtml(err.message)}</div>`;
                info.hidden = true;
            }
        };

        input.addEventListener("input", debouncedAutocomplete);
        input.addEventListener("keydown", (e) => {
            if (e.key === "Enter") {
                e.preventDefault();
                doSearch();
            } else if (e.key === "Escape") {
                acList.hidden = true;
            }
        });

        // Hide autocomplete when clicking outside.
        document.addEventListener("click", (e) => {
            if (!e.target.closest(".search-box")) acList.hidden = true;
        });

        window.doSearch = doSearch;
    }

    function renderSearchResults(cards, total, query) {
        const results = document.getElementById("search-results");
        const info = document.getElementById("search-info");
        if (!cards.length) {
            results.innerHTML = `<div class="search-empty">No cards matched "${escapeHtml(query)}".</div>`;
            info.hidden = true;
            return;
        }
        info.hidden = false;
        info.textContent = `${total} card${total === 1 ? "" : "s"} matched "${query}" (showing ${cards.length}).`;

        results.innerHTML = cards.map(card => {
            const img = card.image_small || "";
            const manaHtml = window.renderMana(card.mana_cost || "");
            return `
                <div class="search-result-card" data-card-id="${escapeHtml(card.id)}">
                    ${img ? `<img src="${img}" alt="${escapeHtml(card.name)}" loading="lazy">` : ""}
                    <div class="sr-info">
                        <div class="sr-name">${escapeHtml(card.name)} ${manaHtml}</div>
                        <div class="sr-type">${escapeHtml(truncate(card.type_line, 40))}</div>
                    </div>
                    <div class="add-btns">
                        <button class="add-btn add-main" data-section="main" title="Add to Main">+M</button>
                        <button class="add-btn add-side" data-section="sideboard" title="Add to Sideboard">+S</button>
                        <button class="add-btn add-maybe" data-section="maybe" title="Add to Maybeboard">+?</button>
                    </div>
                </div>
            `;
        }).join("");

        results.querySelectorAll(".search-result-card").forEach(el => {
            const cardId = el.dataset.cardId;
            // Preview on hover.
            el.addEventListener("mouseenter", () => {
                const card = cards.find(c => c.id === cardId);
                if (card) window.schedulePreview(card, el);
            });
            el.addEventListener("mouseleave", () => window.cancelPreview());
            el.addEventListener("click", (e) => {
                if (e.target.closest("button")) return;
                const card = cards.find(c => c.id === cardId);
                if (card) window.renderPreview(card, el);
            });
            // Add buttons.
            el.querySelectorAll(".add-btn").forEach(btn => {
                btn.addEventListener("click", (e) => {
                    e.stopPropagation();
                    addCard(cardId, btn.dataset.section, 1);
                });
            });
        });
    }

    // ---------------------------------------------------------------------
    // Export dropdown
    // ---------------------------------------------------------------------

    function initExportDropdown() {
        const btn = document.getElementById("export-btn");
        const menu = document.getElementById("export-menu");
        if (!btn || !menu) return;
        btn.addEventListener("click", (e) => {
            e.stopPropagation();
            menu.classList.toggle("open");
        });
        document.addEventListener("click", (e) => {
            if (!e.target.closest(".dropdown")) menu.classList.remove("open");
        });
    }

    // ---------------------------------------------------------------------
    // Initialization
    // ---------------------------------------------------------------------

    document.addEventListener("DOMContentLoaded", async () => {
        initSearch();
        initExportDropdown();
        // Initial entry load.
        try {
            const data = await api(`/api/decks/${DECK_ID}/entries`);
            ingestEntries(data.entries || []);
            renderAllSections();
            initSortable();
            window.refreshStats();
        } catch (err) {
            console.error("Initial load failed:", err);
        }
    });
})();
