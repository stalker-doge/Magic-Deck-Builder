// stats.js — Render mana curve bar chart + color distribution doughnut.
// Requires Chart.js loaded globally.

(function () {
    "use strict";

    const COLOR_HEX = {
        W: "#f3ead2",
        U: "#4f9fd1",
        B: "#7868a0",
        R: "#c2554e",
        G: "#4f8f4a",
        C: "#a8a8a8",
    };

    const COLOR_LABELS = {
        W: "White", U: "Blue", B: "Black", R: "Red", G: "Green", C: "Colorless",
    };

    let manaChart = null;
    let colorChart = null;

    function makeBarGradient(ctx, chartArea) {
        // Metallic gold gradient — like inscribed gold on the mana curve.
        if (!chartArea) return "#c9a961";
        const g = ctx.createLinearGradient(0, chartArea.bottom, 0, chartArea.top);
        g.addColorStop(0, "rgba(138, 106, 42, 0.85)");
        g.addColorStop(0.5, "rgba(201, 169, 97, 0.95)");
        g.addColorStop(1, "rgba(236, 208, 138, 1)");
        return g;
    }

    function initManaChart() {
        const ctxEl = document.getElementById("mana-curve-chart");
        if (!ctxEl) return null;
        const ctx2d = ctxEl.getContext("2d");
        manaChart = new Chart(ctxEl, {
            type: "bar",
            data: {
                labels: ["0", "1", "2", "3", "4", "5", "6", "7+"],
                datasets: [{
                    label: "Cards",
                    data: [0, 0, 0, 0, 0, 0, 0, 0],
                    backgroundColor: (c) => makeBarGradient(c.chart.ctx, c.chart.chartArea),
                    borderColor: "rgba(236, 208, 138, 0.6)",
                    borderWidth: 1,
                    borderRadius: 3,
                    hoverBackgroundColor: "rgba(245, 220, 138, 1)",
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: { duration: 600, easing: "easeOutQuart" },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: "rgba(10, 13, 20, 0.95)",
                        borderColor: "#8a6a2a",
                        borderWidth: 1,
                        titleColor: "#ecd08a",
                        bodyColor: "#cfc4a8",
                        titleFont: { family: "Cinzel, serif", weight: "600", size: 12 },
                        bodyFont: { family: "Hanken Grotesk, sans-serif", size: 12 },
                        padding: 10,
                        cornerRadius: 4,
                        displayColors: false,
                    },
                },
                scales: {
                    x: {
                        grid: { color: "rgba(201,169,97,0.06)", drawBorder: false },
                        ticks: {
                            color: "#8e8772",
                            font: { family: "Cinzel, serif", size: 11, weight: "600" },
                        },
                    },
                    y: {
                        grid: { color: "rgba(201,169,97,0.06)", drawBorder: false },
                        ticks: {
                            color: "#8e8772",
                            font: { family: "Hanken Grotesk, sans-serif", size: 11 },
                            precision: 0,
                            stepSize: 1,
                        },
                        beginAtZero: true,
                    },
                },
            },
        });
        return manaChart;
    }

    function initColorChart() {
        const ctxEl = document.getElementById("color-chart");
        if (!ctxEl) return null;
        colorChart = new Chart(ctxEl, {
            type: "doughnut",
            data: {
                labels: Object.values(COLOR_LABELS),
                datasets: [{
                    data: [0, 0, 0, 0, 0, 0],
                    backgroundColor: Object.values(COLOR_HEX),
                    borderColor: "#0a0d14",
                    borderWidth: 2,
                    hoverOffset: 6,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: { duration: 700, easing: "easeOutQuart", animateRotate: true },
                cutout: "58%",
                plugins: {
                    legend: {
                        position: "right",
                        labels: {
                            color: "#cfc4a8",
                            font: { family: "Hanken Grotesk, sans-serif", size: 11, weight: "500" },
                            boxWidth: 10,
                            boxHeight: 10,
                            padding: 8,
                            usePointStyle: true,
                            pointStyle: "rectRounded",
                        },
                    },
                    tooltip: {
                        backgroundColor: "rgba(10, 13, 20, 0.95)",
                        borderColor: "#8a6a2a",
                        borderWidth: 1,
                        titleColor: "#ecd08a",
                        bodyColor: "#cfc4a8",
                        titleFont: { family: "Cinzel, serif", weight: "600", size: 12 },
                        bodyFont: { family: "Hanken Grotesk, sans-serif", size: 12 },
                        padding: 10,
                        cornerRadius: 4,
                    },
                },
            },
        });
        return colorChart;
    }

    window.refreshStats = async function () {
        if (!manaChart) initManaChart();
        if (!colorChart) initColorChart();

        try {
            const resp = await fetch(`/api/decks/${window.DECK_ID}/stats`);
            if (!resp.ok) return;
            const data = await resp.json();

            const curve = data.mana_curve || {};
            manaChart.data.datasets[0].data = ["0", "1", "2", "3", "4", "5", "6", "7+"].map(k => curve[k] || 0);
            manaChart.update();

            const colors = data.colors || {};
            colorChart.data.datasets[0].data = ["W", "U", "B", "R", "G", "C"].map(k => colors[k] || 0);
            colorChart.update();

            const totals = data.totals || {};
            const totalsList = document.getElementById("totals-list");
            if (totalsList) {
                totalsList.innerHTML = `
                    <div class="total-row"><span>Main Deck</span><strong>${totals.main || 0}</strong></div>
                    <div class="total-row"><span>Sideboard</span><strong>${totals.sideboard || 0}</strong></div>
                    <div class="total-row"><span>Maybeboard</span><strong>${totals.maybe || 0}</strong></div>
                    <div class="total-row" style="margin-top:6px;border-top:1px solid var(--border);padding-top:6px;">
                        <span>Total</span><strong>${totals.all || 0}</strong>
                    </div>
                `;
            }
        } catch (err) {
            console.error("Failed to refresh stats:", err);
        }
    };

    // Initialize on first load.
    document.addEventListener("DOMContentLoaded", () => {
        initManaChart();
        initColorChart();
        window.refreshStats();
    });
})();
