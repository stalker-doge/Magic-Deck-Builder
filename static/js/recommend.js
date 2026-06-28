// recommend.js — Live, deck-aware card recommendations panel.
// Polls /api/decks/{id}/recommendations and renders categorized suggestions
// in the left sidebar under the search results. Re-uses app.js's
// window.renderCardHtml + window.attachCardHandlers so rec cards look and
// behave identically to search-result cards (hover preview, +C/+M/+S/+?
// buttons, click-to-preview).
//
// window.refreshRecommendations() is called by app.js after every addCard
// and removeEntry. Backend cache is content-keyed, so repeated calls are
// cheap when the deck's card-id set hasn't changed.

(function () {
    "use strict";

    let refreshBtn = null;
    let inFlight = false;

    function escapeHtml(s) {
        if (s == null) return "";
        return String(s).replace(/[&<>"']/g, ch => ({
            "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
        }[ch]));
    }

    function renderCategory(cat) {
        // Each category is a labeled block of search-result-style cards.
        // We render cards via the same path as search results so the UI is
        // consistent and handlers (hover preview, add buttons) are reused.
        const cardsHtml = cat.cards.map(window.renderCardHtml).join("");
        return `
            <div class="recs-category" data-cat-id="${escapeHtml(cat.id)}">
                <div class="recs-cat-title">
                    <span>${escapeHtml(cat.label)}</span>
                    <span class="recs-cat-count">${cat.cards.length}</span>
                </div>
                ${cardsHtml}
            </div>
        `;
    }

    function renderEmpty(message) {
        const content = document.getElementById("recs-content");
        if (!content) return;
        content.innerHTML = `<div class="recs-empty">${escapeHtml(message)}</div>`;
    }

    function renderRecommendations(data) {
        const content = document.getElementById("recs-content");
        const section = document.getElementById("recs-section");
        if (!content || !section) return;

        const cats = data.categories || [];
        if (!cats.length) {
            // Empty deck or no themes detected — pick the right hint.
            const msg = data.reason === "empty"
                ? "Add cards to get recommendations."
                : "Add more cards to refine recommendations.";
            renderEmpty(msg);
            return;
        }

        // Collect every card across all categories so attachCardHandlers can
        // build a complete id→card map (needed for hover preview lookups).
        const allCards = [];
        for (const cat of cats) allCards.push(...cat.cards);

        content.innerHTML = cats.map(renderCategory).join("");
        // Wire handlers once across the whole content tree.
        if (window.attachCardHandlers) window.attachCardHandlers(content, allCards);
    }

    async function fetchAndRender() {
        if (inFlight) return;
        const section = document.getElementById("recs-section");
        const content = document.getElementById("recs-content");
        if (!section || !content) return;

        inFlight = true;
        if (refreshBtn) refreshBtn.classList.add("spinning");
        content.innerHTML = `<div class="recs-loading">Analyzing deck…</div>`;

        try {
            const resp = await fetch(`/api/decks/${window.DECK_ID}/recommendations`);
            if (!resp.ok) {
                renderEmpty("Recommendations unavailable.");
                return;
            }
            const data = await resp.json();
            renderRecommendations(data);
        } catch (err) {
            console.error("Recommendation fetch failed:", err);
            renderEmpty("Recommendations unavailable.");
        } finally {
            inFlight = false;
            if (refreshBtn) refreshBtn.classList.remove("spinning");
        }
    }

    // Idempotent public entry point — safe for app.js to call repeatedly.
    window.refreshRecommendations = function () {
        // If the section isn't in the DOM (e.g. a non-editor page), bail fast.
        const section = document.getElementById("recs-section");
        if (!section) return;
        fetchAndRender();
    };

    document.addEventListener("DOMContentLoaded", () => {
        refreshBtn = document.getElementById("recs-refresh");
        if (refreshBtn) {
            refreshBtn.addEventListener("click", () => fetchAndRender());
        }
        // Initial load. Backend cache makes this cheap on repeat visits.
        window.refreshRecommendations();
    });
})();
