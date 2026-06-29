// preview.js — Card hover/click preview panel and mana symbol rendering.
// Requires the Mana font CSS to be loaded.

(function () {
    "use strict";

    const MANA_CLASS = {
        W: "ms-w", U: "ms-u", B: "ms-b", R: "ms-r", G: "ms-g", C: "ms-c",
        // Generic / numeric costs use mana-font icons.
        "1/2": "ms ms-1-2",
        // X and numeric symbols are handled below.
    };

    // Split a mana cost string like "{2}{R}{R}" into tokens.
    function parseManaCost(cost) {
        if (!cost) return [];
        const tokens = [];
        const re = /\{([^}]+)\}/g;
        let m;
        while ((m = re.exec(cost)) !== null) {
            tokens.push(m[1]);
        }
        return tokens;
    }

    // Render a mana cost string as inline HTML with mana font icons.
    window.renderMana = function (cost) {
        const tokens = parseManaCost(cost);
        if (!tokens.length) return "";
        return tokens.map(token => {
            const t = token.toLowerCase();
            // Numeric or X/S etc. → use mana font's "ms-N" classes.
            if (/^[0-9xyz]+$/.test(t)) {
                return `<i class="ms ms-cost ms-${t}"></i>`;
            }
            // Hybrid mana like R/G → "ms-rg"
            if (t.includes("/")) {
                const parts = t.split("/").map(p => p.toLowerCase()).join("");
                return `<i class="ms ms-cost ms-${parts}"></i>`;
            }
            // Phyrexian like R/P
            if (t.length === 1 && /[WUBRGC]/i.test(token)) {
                return `<i class="ms ms-cost ms-${t}"></i>`;
            }
            // Snow, tap etc.
            if (t === "s") return `<i class="ms ms-cost ms-s"></i>`;
            if (t === "t") return `<i class="ms ms-cost ms-tap"></i>`;
            // Fallback: plain text in a colored span.
            return `<i class="ms ms-cost ms-${t}">${token}</i>`;
        }).join("");
    };

    // Render mana cost as colored unicode circles if Mana font not loaded yet.
    window.renderManaFallback = function (cost) {
        const tokens = parseManaCost(cost);
        if (!tokens.length) return "";
        return tokens.map(token => {
            const t = token.toLowerCase();
            if (/^[0-9]+$/.test(t)) {
                return `<span class="mana-pip mana-generic">${token}</span>`;
            }
            const colorClass = MANA_CLASS[token.toUpperCase()];
            if (colorClass) {
                return `<span class="mana-pip ${colorClass}">●</span>`;
            }
            return `<span class="mana-pip mana-generic">${token}</span>`;
        }).join("");
    };

    // -----------------------------------------------------------------
    // Floating preview modal — appears beside the hovered card element.
    // One lazily-built container appended to <body>, repositioned per use.
    // -----------------------------------------------------------------
    const SHOW_DELAY  = 220;  // ms hover grace before showing
    const HIDE_DELAY  = 140;  // ms grace before hiding (lets the mouse cross onto the modal)
    const EDGE_PAD    = 12;   // gap between anchor and modal
    const VIEW_MARGIN = 8;    // min distance from viewport edges

    let modalEl = null;
    let showTimer = null;
    let hideTimer = null;
    let lastAnchor = null;

    function ensureModal() {
        if (modalEl) return modalEl;
        modalEl = document.createElement("div");
        modalEl.className = "preview-modal";
        modalEl.setAttribute("role", "dialog");
        modalEl.setAttribute("aria-hidden", "true");
        document.body.appendChild(modalEl);

        // Hovering the modal itself (e.g. to click a face button) keeps it open.
        modalEl.addEventListener("mouseenter", () => {
            clearTimeout(showTimer);
            clearTimeout(hideTimer);
        });
        modalEl.addEventListener("mouseleave", () => scheduleHide());

        // Keep the modal glued to its anchor while the page scrolls/resizes.
        const reposition = () => { if (modalEl && !modalEl.hidden) positionModal(); };
        window.addEventListener("scroll", reposition, { passive: true, capture: true });
        window.addEventListener("resize", reposition, { passive: true });
        return modalEl;
    }

    // Measure + place the modal beside `lastAnchor`, flipping/clamping to stay on-screen.
    function positionModal() {
        const modal = ensureModal();
        const anchor = lastAnchor;
        if (!anchor) return;

        // CSS `visibility: hidden` keeps the modal non-interactive while still
        // reporting real dimensions, so no attribute toggling is needed.
        const mw = modal.offsetWidth || 256;
        const mh = modal.offsetHeight || 360;

        const r = anchor.getBoundingClientRect();
        const vw = window.innerWidth;
        const vh = window.innerHeight;

        // If the anchor scrolled fully out of view, hide rather than dangle.
        if (r.bottom <= 0 || r.top >= vh || r.right <= 0 || r.left >= vw) {
            hideModal();
            return;
        }

        const spaceRight = vw - r.right - EDGE_PAD;
        const spaceLeft  = r.left - EDGE_PAD;
        let left;
        if (spaceRight >= mw || spaceRight >= spaceLeft) {
            left = r.right + EDGE_PAD;
        } else {
            left = r.left - mw - EDGE_PAD;
        }
        if (left + mw > vw - VIEW_MARGIN) left = vw - mw - VIEW_MARGIN;
        if (left < VIEW_MARGIN) left = VIEW_MARGIN;

        let top = r.top + r.height / 2 - mh / 2;
        if (top + mh > vh - VIEW_MARGIN) top = vh - mh - VIEW_MARGIN;
        if (top < VIEW_MARGIN) top = VIEW_MARGIN;

        modal.style.left = `${Math.round(left)}px`;
        modal.style.top  = `${Math.round(top)}px`;
    }

    function showModal() {
        const modal = ensureModal();
        positionModal();
        modal.setAttribute("aria-hidden", "false");
        modal.classList.add("open");
    }

    function hideModal() {
        clearTimeout(showTimer);
        clearTimeout(hideTimer);
        if (!modalEl) return;
        modalEl.classList.remove("open");
        modalEl.setAttribute("aria-hidden", "true");
    }

    function scheduleHide() {
        clearTimeout(hideTimer);
        hideTimer = setTimeout(hideModal, HIDE_DELAY);
    }

    // Render a card into the floating modal. `anchorEl` is the element the
    // modal should hover beside; optional (omit for a "click to view" refresh).
    window.renderPreview = function (card, anchorEl) {
        if (!card) return;
        const modal = ensureModal();

        // Entries stream multi-face data as a JSON string (card_faces_json);
        // search results already provide card_faces as an array. Normalize.
        let faces = Array.isArray(card.card_faces) ? card.card_faces : null;
        if (!faces && card.card_faces_json) {
            try { faces = JSON.parse(card.card_faces_json); } catch (_) { faces = null; }
        }
        const hasFaces = Array.isArray(faces) && faces.length > 1;

        // Pick the image: top-level first, else first face.
        let image = card.image_normal;
        if (!image && hasFaces) {
            image = (faces[0].image_uris && faces[0].image_uris.normal) || "";
        }

        const manaHtml = window.renderMana(card.mana_cost || "");

        let faceButtons = "";
        if (hasFaces) {
            faceButtons = `<div class="pv-faces">
                <button class="pv-face-btn active" data-face="0">Front</button>
                <button class="pv-face-btn" data-face="1">Back</button>
            </div>`;
        }

        modal.innerHTML = `
            ${faceButtons}
            ${image ? `<img src="${image}" alt="${escapeHtml(card.name)}">` : ""}
            <div class="pv-name">${escapeHtml(card.name)}</div>
            <div class="pv-mana">${manaHtml}</div>
            <div class="pv-type">${escapeHtml(card.type_line || "")}</div>
            <div class="pv-text">${formatOracle(card.oracle_text || "")}</div>
            ${card.power || card.toughness ?
                `<div class="pv-pt"><strong>${escapeHtml(card.power || "")}/${escapeHtml(card.toughness || "")}</strong></div>` : ""}
            <div class="small muted pv-set">
                ${escapeHtml(card.set_name || "")} · ${escapeHtml(card.rarity || "")}
            </div>
        `;

        if (anchorEl) lastAnchor = anchorEl;
        if (lastAnchor) positionModal();

        // Wire face toggle if multi-face.
        if (hasFaces) {
            modal.querySelectorAll(".pv-face-btn").forEach(btn => {
                btn.addEventListener("click", (e) => {
                    e.stopPropagation();
                    const idx = parseInt(btn.dataset.face, 10);
                    const face = faces[idx];
                    if (!face) return;
                    modal.querySelectorAll(".pv-face-btn").forEach(b => b.classList.remove("active"));
                    btn.classList.add("active");

                    const img = modal.querySelector("img");
                    const imgUris = face.image_uris || {};
                    if (img && imgUris.normal) img.src = imgUris.normal;

                    modal.querySelector(".pv-name").textContent = face.name || card.name;
                    modal.querySelector(".pv-mana").innerHTML = window.renderMana(face.mana_cost || "");
                    modal.querySelector(".pv-type").textContent = face.type_line || card.type_line || "";
                    modal.querySelector(".pv-text").innerHTML = formatOracle(face.oracle_text || "");
                });
            });
        }
    };

    // Hover API: show after a short delay, cancel if the mouse leaves first.
    window.schedulePreview = function (card, anchorEl) {
        clearTimeout(hideTimer);
        clearTimeout(showTimer);
        showTimer = setTimeout(() => {
            window.renderPreview(card, anchorEl);
            showModal();
        }, SHOW_DELAY);
    };

    window.cancelPreview = function () {
        clearTimeout(showTimer);
        scheduleHide();
    };

    // Immediate hide (kept for any external / click-to-dismiss callers).
    window.hidePreview = hideModal;
    window.clearPreview = hideModal;

    function escapeHtml(s) {
        if (s == null) return "";
        return String(s)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    function formatOracle(text) {
        return escapeHtml(text)
            .replace(/\n/g, "<br>")
            // Highlight reminder text in parentheses.
            .replace(/\(([^)]+)\)/g, '<span class="muted">($1)</span>');
    }
})();
