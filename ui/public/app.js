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
    currentCycle: 0,
    maxCycle: 0,
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
            // Fetch history for initial engine
            updateHistory(engines[0]);
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
        updateHistory(state.selectedEngine); // Fetch history
    });
}

// --- HISTORY FETCHING ---
async function updateHistory(engineId) {
    try {
        const res = await fetch(`${CONFIG.API_BASE}/history/${engineId}`);
        const data = await res.json();

        if (data.cycles && data.cycles.length > 0) {
            // Set Simulation State
            state.maxCycle = data.cycles[data.cycles.length - 1];
            state.currentCycle = Math.max(0, state.maxCycle - 100); // Start 100 cycles before end

            // Update Degradation Chart immediately with full history (Static Context)
            if (healthChart) {
                healthChart.data.labels = data.cycles;
                healthChart.data.datasets[0].data = data.health;
                healthChart.update();
            }

            // Clear RUL accumulation for new engine
            if (!state.data[engineId]) {
                state.data[engineId] = { history: { rul: [], health: [] } };
            }
            state.data[engineId].history.rul = [];
        }
    } catch (e) {
        console.error("Failed to load history:", e);
    }
}

// --- DATA FETCHING ---
async function fetchData() {
    const id = state.selectedEngine;
    if (!id || !state.maxCycle) return;

    // Simulate Cycle
    // Increment cycle or loop
    state.currentCycle++;
    if (state.currentCycle > state.maxCycle) {
        state.currentCycle = Math.max(0, state.maxCycle - 50); // Loop back slightly
    }

    try {
        // Parallel fetch with cycle param
        const [predictRes] = await Promise.all([
            fetch(`${CONFIG.API_BASE}/predict/${id}?cycle=${state.currentCycle}`)
        ]);

        if (!predictRes.ok) throw new Error("API Error");

        const predData = await predictRes.json();

        // Initialize state for this engine if needed
        if (!state.data[id]) {
            state.data[id] = {
                history: {
                    rul: [], // Use array for accumulation
                    health: []
                }
            };
        }

        const engState = state.data[id];

        // Update current values
        engState.rul = predData.rul_combined;
        engState.rmse = predData.rmse;
        engState.xgbRmse = predData.rmse_xgb;
        engState.transRmse = predData.rmse_transformer;
        engState.window = predData.window;
        engState.health = predData.health; // Now consolidated in predict response
        engState.attention = predData.attention;

        // Accumulate for RUL Forecast Chart (Realtime Uneven Line)
        // Shift if too long
        if (engState.history.rul.length > CONFIG.HISTORY_LENGTH) {
            engState.history.rul.shift();
        }
        engState.history.rul.push(engState.rul);

        // Degradation History:
        // Use full history from /history endpoint for the "past", but maybe append current point?
        // User wants "Degradation history still flat line".
        // Actually, if we use /history, we get the REAL history up to max_cycle presumably.
        // If we want to animate it, we should slice it up to currentCycle.
        // But let's assume updateHistory fetches full history once, and we just show it.
        // Or if user wants real-time, maybe we append?
        // Let's stick to updateHistory for Degradation (it's "History") 
        // and Live Accumulation for RUL Forecast (it's "Forecast" but visualized as live trend).

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
    document.getElementById('rmseValue').textContent = `± ${rmse.toFixed(1)}`;
    document.getElementById('rangeValue').textContent = `${minRange.toFixed(1)} – ${maxRange.toFixed(1)}`;
    document.getElementById('rulError').textContent = `Estimated Error: ± ${rmse.toFixed(1)} cycles`;

    // Model Performance
    if (eng.xgbRmse) document.getElementById('xgbRmseVal').textContent = eng.xgbRmse.toFixed(2);
    if (eng.transRmse) document.getElementById('transRmseVal').textContent = eng.transRmse.toFixed(2);
    if (eng.window) document.getElementById('windowVal').textContent = eng.window;

    // Energy Ring
    // Assuming maxRul is around 300-400 for normalization
    const maxRul = 300;
    updateEnergyRing(eng.rul, maxRul);

    // Health Logic
    const health = Math.max(0, Math.min(100, eng.health)); // Clamp 0-100

    // 1. Text
    // document.getElementById('healthValue').textContent = `${health.toFixed(1)}%`;

    // 2. SVG Gauge Logic
    // Arc length for radius 80 semi-circle is approx 251.3
    const maxDash = 251.3;
    // Invert: 100% health = 0 offset (full bar). 0% health = 251.3 offset (empty).
    // Actually typically gauge fills from left (0) to right (100).
    // If 0 offset is full, then we want to start empty?
    // Let's assume path is drawn left to right.
    // If dashArray is 251.3.
    // dashOffset = 251.3 * (1 - health/100).

    // BUT we want "filled" part to represent health.
    const offset = maxDash * (1 - (health / 100));

    const gaugePath = document.getElementById('healthGaugePath');
    const gaugeValue = document.getElementById('healthGaugeValue');
    const statusPill = document.getElementById('healthStatusPill');

    if (gaugePath) {
        gaugePath.style.strokeDashoffset = offset;
    }

    if (gaugeValue) {
        gaugeValue.textContent = `${Math.round(health)}%`;
    }

    // 3. Status Pill Logic
    let statusText = "NOMINAL";
    let statusClass = "health-status-pill nominal";

    if (health < 40) {
        statusText = "CRITICAL";
        statusClass = "health-status-pill critical";
    } else if (health < 70) {
        statusText = "WARNING";
        statusClass = "health-status-pill warning";
    }

    if (statusPill) {
        statusPill.textContent = statusText;
        statusPill.className = statusClass;
    }

    // Charts & Heatmap
    updateCharts(eng);
    updateHeatmap(eng.attention);
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
                y: { grid: { color: 'rgba(0,0,0,0.05)' } }
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
                y: { min: 0, max: 300, grid: { color: 'rgba(0,0,0,0.05)' } }
            },
            animation: false
        }
    });
}

// --- FORECAST GENERATION ---
function generateForecast(currentRul) {
    const points = [];
    let val = currentRul;

    // Generate 50 points of decay
    for (let i = 0; i < 50; i++) {
        val -= 1 + Math.random() * 0.4;  // nonlinear decay
        if (val < 0) val = 0;
        points.push(val);
    }
    return points;
}

function updateCharts(eng) {
    // 1. Health Chart is handled by updateHistory() (Full History Context)

    // 2. RUL Forecast Chart: Show Live Accumulation + Forecast
    if (rulChart) {
        // Show the accumulated history of predictions (The "Uneven Line")
        // And maybe project from the last point?
        // User asked for "Realtime with changing value... uneven line".
        // Simply plotting the accumulated history of 'rul' predictions gives us that uneven line.
        // We can append the decay forecast to it if we want, but let's stick to the
        // "Live Trend" of the prediction itself as it moves.

        const liveData = eng.history.rul;

        // Ensure labels match
        const labels = Array(liveData.length).fill('');

        rulChart.data.labels = labels;
        rulChart.data.datasets[0].data = liveData;
        rulChart.update();
    }
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

function updateHeatmap(attentionData) {
    if (!attentionData || !attentionData.length) return;

    // Auto-detect dimensions
    const rows = attentionData.length;
    const cols = attentionData[0].length;

    // Canvas dimensions
    // We want to fill the canvas 300x150
    const w = 300;
    const h = 150;
    const cellW = w / cols;
    const cellH = h / rows;

    heatmapCtx.clearRect(0, 0, w, h);

    // Normalize ? Usually attention weights sum to 1 per row. 
    // They might be very small. 
    // Let's find max value for scaling visibility
    let maxVal = 0;
    for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
            if (attentionData[r][c] > maxVal) maxVal = attentionData[r][c];
        }
    }

    const scale = maxVal > 0 ? (1.0 / maxVal) : 1;

    for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
            // Value
            const val = attentionData[r][c] * scale;

            // Color mapping: 
            // Heatmap style: Blue (Low) -> Red (High) or just Blue Opacity?
            // User UI showed Blue blocks.
            // Let's use Opacity of a strong Blue/Purple.

            // Threshold for visibility? 
            // Using alpha
            // const alpha = Math.min(1, val * 2.0); // Boost contrast

            // Actually attention map is often diagonal.
            // Let's use simple blue
            // Ensure min visibility
            const alpha = 0.1 + (val * 0.9);

            heatmapCtx.fillStyle = `rgba(0, 122, 255, ${alpha})`;

            // Rounded rects for clearer "tech" look on white
            // Adjust cell size slightly for gap
            heatmapCtx.beginPath();
            heatmapCtx.roundRect(c * cellW + 0.5, r * cellH + 0.5, cellW - 1, cellH - 1, 1);
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

