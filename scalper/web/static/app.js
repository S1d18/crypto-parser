/* ===== Sniper Scalper Bot — Dashboard JS ===== */

const POLL_INTERVAL = 5000;

const CLOSE_REASONS = {
    tp: 'Take Profit',
    tp_hit: 'Take Profit',
    sl: 'Stop Loss',
    sl_hit: 'Stop Loss',
    signal: 'Сигнал',
    manual: 'Вручную',
    trailing: 'Trailing Stop',
};

/* ---------- Chart.js setup ---------- */
let equityChart = null;

function initChart() {
    const ctx = document.getElementById('equity-chart').getContext('2d');
    equityChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Баланс',
                data: [],
                borderColor: '#448aff',
                backgroundColor: 'rgba(68, 138, 255, 0.1)',
                fill: true,
                tension: 0.3,
                pointRadius: 0,
                pointHitRadius: 8,
                borderWidth: 2,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: function(ctx) {
                            return '$' + ctx.parsed.y.toFixed(2);
                        },
                    },
                },
            },
            scales: {
                x: {
                    ticks: { color: '#8888aa', maxTicksLimit: 10 },
                    grid: { color: 'rgba(255,255,255,0.05)' },
                },
                y: {
                    ticks: {
                        color: '#8888aa',
                        callback: function(v) { return '$' + v.toFixed(0); },
                    },
                    grid: { color: 'rgba(255,255,255,0.05)' },
                },
            },
        },
    });
}

/* ---------- UI Helpers ---------- */

function $(id) { return document.getElementById(id); }

function pnlClass(val) {
    return val >= 0 ? 'pnl-positive' : 'pnl-negative';
}

function formatPnl(val) {
    const sign = val >= 0 ? '+' : '';
    return sign + '$' + val.toFixed(2);
}

function formatTime(iso) {
    if (!iso) return '—';
    const d = new Date(iso);
    return d.toLocaleString('ru-RU', {
        day: '2-digit', month: '2-digit',
        hour: '2-digit', minute: '2-digit',
    });
}

function translateReason(reason) {
    if (!reason) return '—';
    return CLOSE_REASONS[reason] || reason;
}

/* ---------- Update Functions ---------- */

function updateStatus(data) {
    const badge = $('status-badge');
    if (data.running) {
        if (data.can_trade) {
            badge.textContent = 'Работает';
            badge.className = 'badge badge-running';
        } else {
            badge.textContent = 'Пауза';
            badge.className = 'badge badge-paused';
        }
    } else {
        badge.textContent = 'Остановлен';
        badge.className = 'badge badge-stopped';
    }

    $('metric-balance').textContent = '$' + (data.balance || 0).toFixed(2);

    const daily = data.daily_stats || {};
    const all = data.all_stats || {};

    const dailyPnl = daily.total_pnl || 0;
    const dailyEl = $('metric-daily-pnl');
    dailyEl.textContent = formatPnl(dailyPnl);
    dailyEl.className = 'metric-value ' + pnlClass(dailyPnl);

    $('metric-daily-trades').textContent = daily.total_trades || 0;

    const winrate = all.win_rate || 0;
    $('metric-winrate').textContent = winrate.toFixed(1) + '%';

    const totalPnl = all.total_pnl || 0;
    const totalPnlEl = $('metric-total-pnl');
    totalPnlEl.textContent = formatPnl(totalPnl);
    totalPnlEl.className = 'metric-value ' + pnlClass(totalPnl);

    $('metric-total-trades').textContent = all.total_trades || 0;

    // Positions
    updatePositions(data.positions || []);
}

function updatePositions(positions) {
    const container = $('position-content');
    if (!positions.length) {
        container.innerHTML = '<p class="no-data">Нет открытых позиций</p>';
        return;
    }

    let html = '';
    for (const p of positions) {
        const dirClass = p.direction === 'long' ? 'direction-long' : 'direction-short';
        const dirLabel = p.direction === 'long' ? 'LONG' : 'SHORT';
        html += `
        <div class="position-row">
            <div class="position-field">
                <span class="position-field-label">Монета</span>
                <span class="position-field-value">${p.symbol}</span>
            </div>
            <div class="position-field">
                <span class="position-field-label">Направление</span>
                <span class="position-field-value ${dirClass}">${dirLabel}</span>
            </div>
            <div class="position-field">
                <span class="position-field-label">Вход</span>
                <span class="position-field-value">$${p.entry_price.toFixed(4)}</span>
            </div>
            <div class="position-field">
                <span class="position-field-label">SL</span>
                <span class="position-field-value pnl-negative">$${p.sl_price.toFixed(4)}</span>
            </div>
            <div class="position-field">
                <span class="position-field-label">TP</span>
                <span class="position-field-value pnl-positive">$${p.tp_price.toFixed(4)}</span>
            </div>
            <div class="position-field">
                <span class="position-field-label">Объём</span>
                <span class="position-field-value">${p.qty}</span>
            </div>
        </div>`;
    }
    container.innerHTML = html;
}

function updateTrades(trades) {
    const tbody = $('trades-tbody');
    if (!trades.length) {
        tbody.innerHTML = '<tr><td colspan="7" class="no-data">Нет завершённых сделок</td></tr>';
        return;
    }

    let html = '';
    for (const t of trades) {
        const dirClass = t.direction === 'long' ? 'direction-long' : 'direction-short';
        const dirLabel = t.direction === 'long' ? 'LONG' : 'SHORT';
        const pnl = t.pnl || 0;
        const pnlPct = t.pnl_pct || 0;
        html += `<tr>
            <td>${formatTime(t.closed_at)}</td>
            <td>${t.symbol}</td>
            <td class="${dirClass}">${dirLabel}</td>
            <td>$${t.entry_price.toFixed(4)}</td>
            <td>${t.exit_price ? '$' + t.exit_price.toFixed(4) : '—'}</td>
            <td class="${pnlClass(pnl)}">${formatPnl(pnl)} (${pnlPct.toFixed(1)}%)</td>
            <td>${translateReason(t.close_reason)}</td>
        </tr>`;
    }
    tbody.innerHTML = html;
}

function updateEquityChart(equity) {
    if (!equityChart || !equity.length) return;

    const labels = equity.map(e => {
        const d = new Date(e.timestamp);
        return d.toLocaleString('ru-RU', {
            day: '2-digit', month: '2-digit',
            hour: '2-digit', minute: '2-digit',
        });
    });
    const values = equity.map(e => e.balance);

    equityChart.data.labels = labels;
    equityChart.data.datasets[0].data = values;
    equityChart.update('none');
}

/* ---------- Polling ---------- */

async function fetchAll() {
    try {
        const [statusRes, tradesRes, equityRes] = await Promise.all([
            fetch('/api/status'),
            fetch('/api/trades'),
            fetch('/api/equity'),
        ]);
        const status = await statusRes.json();
        const trades = await tradesRes.json();
        const equity = await equityRes.json();

        updateStatus(status);
        updateTrades(trades);
        updateEquityChart(equity);
    } catch (err) {
        console.error('Fetch error:', err);
    }
}

/* ---------- Socket.IO ---------- */

function initSocket() {
    try {
        const socket = io();

        socket.on('connect', () => {
            console.log('Socket.IO connected');
        });

        socket.on('trade_opened', () => {
            fetchAll();
        });

        socket.on('trade_closed', () => {
            fetchAll();
        });

        socket.on('started', () => {
            fetchAll();
        });

        socket.on('stopped', () => {
            fetchAll();
        });
    } catch (err) {
        console.warn('Socket.IO not available, using polling only');
    }
}

/* ---------- Init ---------- */

document.addEventListener('DOMContentLoaded', () => {
    initChart();
    fetchAll();
    initSocket();
    setInterval(fetchAll, POLL_INTERVAL);
});
