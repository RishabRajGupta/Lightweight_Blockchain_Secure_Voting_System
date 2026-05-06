const root = document.documentElement;
const body = document.body;

const storedTheme = localStorage.getItem("securevote-theme");
if (storedTheme) {
    root.dataset.theme = storedTheme;
}

const storedSidebar = localStorage.getItem("securevote-sidebar");
if (storedSidebar === "collapsed") {
    body.classList.add("sidebar-collapsed");
}

function refreshIcons() {
    if (window.lucide) {
        window.lucide.createIcons();
    }
}

function syncSidebarButtons() {
    const collapsed = body.classList.contains("sidebar-collapsed");
    document.querySelectorAll("[data-sidebar-collapse]").forEach((button) => {
        button.querySelector("span").textContent = collapsed ? "Expand" : "Collapse";
        button.querySelector("svg")?.remove();
        button.querySelector("i")?.remove();
        button.insertAdjacentHTML("afterbegin", `<i data-lucide="${collapsed ? "panel-left-open" : "panel-left-close"}"></i>`);
    });
    refreshIcons();
}

function setTheme(theme) {
    root.dataset.theme = theme;
    localStorage.setItem("securevote-theme", theme);
    document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
        button.setAttribute("aria-label", `Switch to ${theme === "dark" ? "light" : "dark"} mode`);
    });
}

document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
        setTheme(root.dataset.theme === "dark" ? "light" : "dark");
    });
});

document.querySelectorAll("[data-sidebar-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
        document.getElementById("sidebar")?.classList.toggle("open");
    });
});

document.querySelectorAll("[data-sidebar-collapse]").forEach((button) => {
    button.addEventListener("click", () => {
        body.classList.toggle("sidebar-collapsed");
        const collapsed = body.classList.contains("sidebar-collapsed");
        localStorage.setItem("securevote-sidebar", collapsed ? "collapsed" : "expanded");
        syncSidebarButtons();
    });
});

document.querySelectorAll(".candidate-card").forEach((card) => {
    card.addEventListener("click", () => {
        const input = card.querySelector("input");
        if (input) input.checked = true;
    });
});

document.querySelectorAll("[data-toast-close]").forEach((button) => {
    button.addEventListener("click", () => {
        button.closest(".app-toast")?.remove();
    });
});

document.querySelectorAll("[data-copy]").forEach((button) => {
    button.addEventListener("click", async () => {
        await navigator.clipboard.writeText(button.dataset.copy || "");
        const previous = button.innerHTML;
        button.innerHTML = '<i data-lucide="check"></i>';
        refreshIcons();
        setTimeout(() => {
            button.innerHTML = previous;
            refreshIcons();
        }, 1100);
    });
});

document.querySelectorAll("[data-scroll-target]").forEach((button) => {
    button.addEventListener("click", () => {
        document.getElementById(button.dataset.scrollTarget)?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
});

document.querySelectorAll("[data-table-search]").forEach((input) => {
    input.addEventListener("input", () => {
        const table = document.querySelector(input.dataset.tableSearch);
        const query = input.value.trim().toLowerCase();
        table?.querySelectorAll("tbody tr").forEach((row) => {
            row.hidden = !row.textContent.toLowerCase().includes(query);
        });
    });
});

document.querySelectorAll("[data-count]").forEach((node) => {
    const target = Number(node.dataset.count || "0");
    if (!Number.isFinite(target) || target === 0) return;
    let frame = 0;
    const frames = 34;
    const tick = () => {
        frame += 1;
        node.textContent = Math.round((target * frame) / frames);
        if (frame < frames) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
});

document.querySelectorAll("[data-progress]").forEach((bar) => {
    requestAnimationFrame(() => {
        bar.style.width = `${bar.dataset.progress}%`;
    });
});

function chartDefaults() {
    if (!window.Chart) return;
    Chart.defaults.color = getComputedStyle(root).getPropertyValue("--muted").trim();
    Chart.defaults.borderColor = "rgba(148, 163, 184, .16)";
    Chart.defaults.font.family = "Inter, system-ui, sans-serif";
}

function renderResultsChart() {
    const canvas = document.getElementById("resultsChart");
    if (!canvas || !window.Chart) return;
    const labels = JSON.parse(canvas.dataset.labels || "[]");
    const values = JSON.parse(canvas.dataset.values || "[]");
    new Chart(canvas, {
        type: "doughnut",
        data: {
            labels,
            datasets: [{
                data: values,
                backgroundColor: ["#39d0c4", "#8b5cf6", "#f6c76b", "#6aa7ff", "#43e0a4"],
                borderWidth: 0,
                hoverOffset: 8
            }]
        },
        options: {
            cutout: "66%",
            plugins: {
                legend: {
                    position: "bottom",
                    labels: { usePointStyle: true, padding: 18 }
                }
            }
        }
    });
}

function renderBenchmarkChart() {
    document.querySelectorAll("#benchmarkChart").forEach((canvas) => {
        if (!window.Chart) return;
        const validator = Number(canvas.dataset.validator || "0");
        const pow = Number(canvas.dataset.pow || "0");
        new Chart(canvas, {
            type: "bar",
            data: {
                labels: ["Validator consensus", "PoW baseline"],
                datasets: [{
                    label: "Milliseconds",
                    data: [validator, pow],
                    backgroundColor: ["#39d0c4", "#ff6b7a"],
                    borderRadius: 8
                }]
            },
            options: {
                plugins: { legend: { display: false } },
                scales: { y: { beginAtZero: true } }
            }
        });
    });
}

function renderLatencyChart() {
    const canvas = document.getElementById("latencyChart");
    if (!canvas || !window.Chart) return;
    new Chart(canvas, {
        type: "radar",
        data: {
            labels: ["Validation", "Signature", "Creation", "Verification", "Consensus"],
            datasets: [{
                label: "Milliseconds",
                data: [
                    Number(canvas.dataset.validation || "0"),
                    Number(canvas.dataset.signature || "0"),
                    Number(canvas.dataset.creation || "0"),
                    Number(canvas.dataset.verification || "0"),
                    Number(canvas.dataset.consensus || "0")
                ],
                borderColor: "#39d0c4",
                backgroundColor: "rgba(57, 208, 196, .18)",
                pointBackgroundColor: "#f6c76b"
            }]
        },
        options: { plugins: { legend: { display: false } } }
    });
}

chartDefaults();
renderResultsChart();
renderBenchmarkChart();
renderLatencyChart();
syncSidebarButtons();
refreshIcons();
