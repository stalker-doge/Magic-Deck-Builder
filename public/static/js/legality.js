// legality.js — Live Commander-format legality panel.
// Polls /api/decks/{id}/legality after every deck mutation and renders a
// compact status panel (commander, color identity, singleton, size).
// Also exposes window.COMMANDER_COLOR_IDENTITY for app.js to filter the
// basic-land toolbar, and window.refreshLegality for app.js to call.

(function () {
    "use strict";

    // Cached commander color identity (WUBRG list). Empty when no commander
    // is set — app.js uses this to disable off-color basic-land pips.
    window.COMMANDER_COLOR_IDENTITY = [];

    function escapeHtml(s) {
        if (s == null) return "";
        return String(s).replace(/[&<>"']/g, ch => ({
            "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
        }[ch]));
    }

    function renderManaPip(color) {
        // Renders a single colored mana pip; colorless ("C") shows a dim ring.
        const code = (color || "").toLowerCase();
        if (!code) return "";
        return `<i class="ms ms-cost ms-${escapeHtml(code)}" aria-hidden="true"></i>`;
    }

    function row(label, valueHtml, modifier) {
        const cls = modifier ? `total-row ${modifier}` : "total-row";
        return `<div class="${cls}"><span>${escapeHtml(label)}</span><strong>${valueHtml}</strong></div>`;
    }

    // Header row (with count) followed by an expanded list of the offending
    // cards when there are any. `renderItem` builds the per-card row HTML
    // from a violation object — its shape differs per check.
    function renderViolationBlock(label, violations, ok, renderItem) {
        const list = Array.isArray(violations) ? violations : [];
        const header = row(label, String(list.length), ok ? "" : "illegal");
        if (!list.length) return header;
        return `${header}<div class="violation-list">${list.map(renderItem).join("")}</div>`;
    }

    window.refreshLegality = async function () {
        const block = document.getElementById("legality-block");
        if (!block) return;

        // Only commander-format decks show the panel.
        if ((window.DECK_FORMAT || "casual") !== "commander") {
            block.hidden = true;
            window.COMMANDER_COLOR_IDENTITY = [];
            if (window.updateBasicsDisabledState) window.updateBasicsDisabledState();
            return;
        }
        block.hidden = false;

        try {
            const resp = await fetch(`/api/decks/${window.DECK_ID}/legality`);
            if (!resp.ok) return;
            const report = await resp.json();
            renderLegality(report);
        } catch (err) {
            console.error("Legality refresh failed:", err);
        }
    };

    function renderLegality(report) {
        const list = document.getElementById("legality-list");
        if (!list) return;
        const checks = report.checks || {};
        const cmd = checks.commander || {};
        const ci = checks.color_identity || {};
        const sg = checks.singleton || {};
        const sz = checks.size || {};

        // Cache commander color identity for the basics toolbar.
        window.COMMANDER_COLOR_IDENTITY = ci.allowed || [];
        if (window.updateBasicsDisabledState) window.updateBasicsDisabledState();

        const headClass = report.legal ? "legal" : "illegal";
        const headGlyph = report.legal ? "✓ Legal" : "✗ Issues";
        const pipHtml = (ci.allowed || []).map(renderManaPip).join("") || "—";

        const commanderNames = (cmd.names && cmd.names.length)
            ? cmd.names.map(escapeHtml).join(" <span class='legality-dim'>+</span> ")
            : "—";
        const pairingLabel = cmd.pairing
            ? cmd.pairing.replace(/_/g, " ")
            : "";

        const parts = [];
        parts.push(`<div class="legality-head ${headClass}">${headGlyph}</div>`);
        parts.push(row("Commander", commanderNames));
        if (pairingLabel) {
            parts.push(`<div class="total-row"><span class="legality-dim">Pairing</span><span class="legality-dim">${escapeHtml(pairingLabel)}</span></div>`);
        }
        if (cmd.message) {
            parts.push(`<div class="legality-warn">${escapeHtml(cmd.message)}</div>`);
        }
        parts.push(`<div class="total-row"><span>Color identity</span><span class="legality-pips">${pipHtml}</span></div>`);
        parts.push(renderViolationBlock(
            "Color violations",
            ci.violations,
            ci.ok,
            (v) => {
                const excessHtml = (v.excess || []).map(renderManaPip).join("")
                    || "<span class='legality-dim'>—</span>";
                return `<div class="violation-item"><span class="violation-name" title="${escapeHtml(v.name)}">${escapeHtml(v.name)}</span><span class="violation-pips">${excessHtml}</span></div>`;
            }
        ));
        parts.push(renderViolationBlock(
            "Singleton violations",
            sg.violations,
            sg.ok,
            (v) => `<div class="violation-item"><span class="violation-name" title="${escapeHtml(v.name)}">${escapeHtml(v.name)}</span><span class="violation-qty">×${v.quantity}</span></div>`
        ));
        parts.push(row("Size", `${sz.actual || 0}/${sz.target || 100}`, sz.ok ? "" : "illegal"));

        list.innerHTML = parts.join("");
    }

    document.addEventListener("DOMContentLoaded", () => {
        window.refreshLegality();
    });
})();
