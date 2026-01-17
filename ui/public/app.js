/* 
   Trustworthy AI Digital Twin — RUL Prediction System 
   Core Application Logic
*/

// --- CONFIGURATION ---
const CONFIG = {
    API_BASE: 'http://127.0.0.1:5000',
    UPDATE_INTERVAL: 2000,
    HISTORY_LENGTH: 50
};

// --- STATE MANAGEMENT ---
const state = {
    selectedEngine: null,
    data: {}, // Cache for history: { engineId: { rul, health, history: { rul: [], health: [] } } }
};

// --- INITIALIZATION ---
document.addEventListener('DOMContentLoaded', async () => {
    initCharts();
    initHeatmap();

    // 1. Fetch Engines & Initialize
    await initEngineSelector();

    // Start Realtime Loop
    // Initial fetch
    if (state.selectedEngine) {
        fetchData();
    }

    // Loop
    setInterval(() => {
        if (state.selectedEngine) {
            fetchData();
        }
    }, CONFIG.UPDATE_INTERVAL);
});

// --- ENGINE SELECTOR (Updated) ---
async function initEngineSelector() {
    const select = document.getElementById('engineSelect');

    try {
        const res = await fetch(`${CONFIG.API_BASE}/engines`);
        const engines = await res.json();

        // Clear loading state if any (not present in current HTML but good practice)
        select.innerHTML = '';

        engines.forEach(eid => {
            const opt = document.createElement('option');
            opt.value = eid;
            opt.textContent = eid.toUpperCase(); // Display as ENGINE-1 e.g.
            select.appendChild(opt);
        });

        // Select first one by default
        if (engines.length > 0) {
            state.selectedEngine = engines[0];
            select.value = engines[0];
        }

    } catch (e) {
        console.error("Failed to load engines:", e);
        const opt = document.createElement('option');
        opt.textContent = "Connection Failed";
        select.appendChild(opt);
    }

    // Listener
    select.addEventListener('change', (e) => {
        state.selectedEngine = e.target.value;
        fetchData(); // Trigger immediate update
    });
}

// --- DATA FETCHING ---
async function fetchData() {
    const id = state.selectedEngine;
    if (!id) return;

    try {
        // Parallel fetch
        const [predictRes, healthRes] = await Promise.all([
            fetch(`${CONFIG.API_BASE}/predict/${id}`),
            fetch(`${CONFIG.API_BASE}/health/${id}`)
        ]);

        if (!predictRes.ok || !healthRes.ok) throw new Error("API Error");

        const predData = await predictRes.json();
        const healthData = await healthRes.json();

        // Initialize state for this engine if needed
        if (!state.data[id]) {
            state.data[id] = {
                history: {
                    rul: Array(CONFIG.HISTORY_LENGTH).fill(0), // Fill 0 or null
                    health: Array(CONFIG.HISTORY_LENGTH).fill(0)
                }
            };
        }

        const engState = state.data[id];

        // Update current values
        // Update current values
        engState.rul = predData.rul_combined;
        engState.rmse = predData.rmse;
        engState.health = healthData.health; // 0-100 based on backend logic

        // Update History (Shift & Push)
        engState.history.rul.shift();
        engState.history.rul.push(engState.rul);

        engState.history.health.shift();
        engState.history.health.push(engState.health);

        // Update UI
        updateUI(engState);

    } catch (e) {
        console.error("Fetch Data Error:", e);
    }
}

// --- UI UPDATES ---
function updateUI(eng) {
    if (!eng) return;

    // RUL Hero
    // RUL Hero
    document.getElementById('rulValue').textContent = eng.rul.toFixed(1);

    const rmse = eng.rmse;
    const minRange = Math.max(0, eng.rul - rmse);
    const maxRange = eng.rul + rmse;

    document.getElementById('rmseValue').textContent = `± ${rmse.toFixed(1)}`;
    document.getElementById('rangeValue').textContent = `${minRange.toFixed(1)} – ${maxRange.toFixed(1)}`;
    document.getElementById('rulError').textContent = `Estimated Error: ± ${rmse.toFixed(1)} cycles`;

    // Energy Ring
    // Assuming maxRul is around 300-400 for normalization
    const maxRul = 400;
    updateEnergyRing(eng.rul, maxRul);

    // Health Logic
    const health = Math.max(0, Math.min(100, eng.health)); // Clamp 0-100

    // 1. Text
    document.getElementById('healthValue').textContent = `${health.toFixed(1)}%`;

    // 2. Gauge Mask (CSS Variable)
    // Request: Convert to degrees: percent * 1.8
    const deg = health * 1.8;
    const gaugeMask = document.getElementById('gaugeMask');
    // We pass degrees directly. CSS conic-gradient needs to handle it.
    // If CSS expects %, we might need to adjust. 
    // BUT the request explicitly asked to set variable to result of percent * 1.8.
    // Assuming 'deg' unit is needed or implicit in usage. 
    // Setting it as degrees string "180deg".
    gaugeMask.style.setProperty('--gauge-percent', `${deg}deg`);

    // 3. Status Pill Logic
    const statusLabel = document.getElementById('healthStatusLabel');
    const gaugeFill = document.getElementById('gaugeFill');

    let statusText = "NOMINAL";
    let statusClass = "health-pill status-nominal";
    let fillClass = "gauge-fill nominal";

    if (health < 40) {
        statusText = "CRITICAL";
        statusClass = "health-pill status-critical";
        fillClass = "gauge-fill critical";
    } else if (health < 70) {
        statusText = "WARNING";
        statusClass = "health-pill status-warning";
        fillClass = "gauge-fill warning";
    }

    // Apply text/classes
    statusLabel.textContent = statusText;
    statusLabel.className = statusClass;

    // Apply gauge fill class (requires removing others first or just overwriting className)
    if (gaugeFill) {
        gaugeFill.className = fillClass;
        // Ensure inline background is cleared so class styles apply (from previous logic)
        gaugeFill.style.background = '';
    }

    // Charts & Heatmap
    updateCharts(eng);
    updateHeatmap(); // Still random for now as no backend endpoint for attention
}



// --- CHARTS (Chart.js) ---
let healthChart, rulChart;

function initCharts() {
    // Safety check for Chart.js
    if (typeof Chart === 'undefined') {
        console.warn("Chart.js not loaded. Charts will be disabled.");
        document.querySelectorAll('.chart-container').forEach(el => el.innerHTML = '<div style="color:red; padding:20px;">Chart Lib Failed</div>');
        return;
    }

    Chart.defaults.color = '#86868b'; // Soft Grey for text
    Chart.defaults.font.family = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";

    // Health Chart
    const ctxHealth = document.getElementById('healthChart').getContext('2d');
    healthChart = new Chart(ctxHealth, {
        type: 'line',
        data: {
            labels: Array(CONFIG.HISTORY_LENGTH).fill(''),
            datasets: [{
                label: 'Health Index',
                data: [],
                borderColor: '#0056b3', // Stronger Blue
                backgroundColor: 'rgba(0, 122, 255, 0.15)',
                borderWidth: 2,
                fill: true,
                tension: 0.4,
                pointRadius: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                x: { display: false },
                y: { min: 0, max: 120, grid: { color: 'rgba(0,0,0,0.05)' } }
            },
            animation: false
        }
    });

    // RUL Chart
    const ctxRul = document.getElementById('rulChart').getContext('2d');
    rulChart = new Chart(ctxRul, {
        type: 'line',
        data: {
            labels: Array(CONFIG.HISTORY_LENGTH).fill(''),
            datasets: [{
                label: 'RUL Forecast',
                data: [],
                borderColor: '#4a00e0', // Stronger Purple
                backgroundColor: 'rgba(88, 86, 214, 0.15)',
                borderWidth: 2,
                fill: true,
                tension: 0.4,
                pointRadius: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                x: { display: false },
                y: { min: 0, max: 400, grid: { color: 'rgba(0,0,0,0.05)' } }
            },
            animation: false
        }
    });
}

function updateCharts(eng) {
    if (!healthChart || !rulChart) return;

    healthChart.data.datasets[0].data = eng.history.health;
    healthChart.update();

    rulChart.data.datasets[0].data = eng.history.rul;
    rulChart.update();
}

// --- HEATMAP (Canvas Digital Rain/Grid) ---
let heatmapCtx;
function initHeatmap() {
    const canvas = document.getElementById('attentionCanvas');
    // Set resolution match CSS size (approx) or keep it fixed internal res
    canvas.width = 300;
    canvas.height = 150;
    heatmapCtx = canvas.getContext('2d');
}

function updateHeatmap() {
    const w = 300;
    const h = 150;
    const cols = 20;
    const rows = 10;
    const cellW = w / cols;
    const cellH = h / rows;

    heatmapCtx.clearRect(0, 0, w, h);

    for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
            // Random intensity for "Attention"
            const intensity = Math.random();
            const isHigh = intensity > 0.85;

            // Color mapping: Light Mode
            // High Attention = Deep Blue (#007AFF)
            // Low Attention = Light Grey/Blue Tint
            if (isHigh) {
                heatmapCtx.fillStyle = `rgba(0, 122, 255, ${0.4 + Math.random() * 0.4})`;
            } else {
                heatmapCtx.fillStyle = `rgba(0, 122, 255, ${Math.random() * 0.1})`;
            }

            // Rounded rects for clearer "tech" look on white
            heatmapCtx.beginPath();
            heatmapCtx.roundRect(c * cellW + 1, r * cellH + 1, cellW - 2, cellH - 2, 2);
            heatmapCtx.fill();
        }
    }
}

function updateEnergyRing(currentRUL, maxRUL) {
    const ring = document.getElementById("energyRingProgress");

    const radius = 96;
    const circumference = 2 * Math.PI * radius;

    const percent = Math.max(0, Math.min(1, currentRUL / maxRUL));
    const offset = circumference * (1 - percent);

    ring.style.strokeDasharray = circumference;
    ring.style.strokeDashoffset = offset;

    // Color logic
    if (percent > 0.6) {
        ring.style.stroke = "url(#ringGradient)";
    } else if (percent > 0.3) {
        ring.style.stroke = "#FF9500";
    } else {
        ring.style.stroke = "#FF3B30";
    }
}

