/**
 * Strategy Detail Page — TradingView-style
 */

let strategyId = null;
let strategyData = null;
let socket = null;
let equityChart = null;

// ============================================================
// Initialization
// ============================================================
document.addEventListener('DOMContentLoaded', function() {
    const pathParts = window.location.pathname.split('/');
    strategyId = pathParts[pathParts.length - 1];

    loadStrategy();
    initWebSocket();

    document.getElementById('refresh-btn').addEventListener('click', loadStrategy);
    document.getElementById('trades-filter').addEventListener('change', function() {
        filterTrades(this.value);
    });

    lucide.createIcons();
});

// ============================================================
// Tab switching
// ============================================================
function switchTab(tab) {
    document.querySelectorAll('.strategy-tabs .tab').forEach(t => t.classList.remove('active'));
    document.querySelector(`.tab[data-tab="${tab}"]`).classList.add('active');

    document.getElementById('tab-metrics').style.display = tab === 'metrics' ? 'block' : 'none';
    document.getElementById('tab-trades').style.display = tab === 'trades' ? 'block' : 'none';
}

// ============================================================
// API
// ============================================================
async function loadStrategy() {
    showLoading();
    try {
        const response = await fetch(`/api/strategies/${strategyId}`);
        const data = await response.json();

        if (data.status === 'ok') {
            strategyData = {
                ...data.strategy,
                statistics: data.statistics,
                trades: data.trades || [],
                equity_curve: data.equity_curve || []
            };
        } else {
            throw new Error(data.message || 'Strategy not found');
        }

        renderStrategy();
    } catch (error) {
        console.error('Error loading strategy:', error);
        showError('Не удалось загрузить стратегию: ' + error.message);
    }
}

// ============================================================
// WebSocket
// ============================================================
function initWebSocket() {
    socket = io();
    socket.on('connect', () => {
        if (strategyId) socket.emit('subscribe', { strategy_id: strategyId });
    });
    socket.on('trade_update', () => loadStrategy());
}

// ============================================================
// Rendering
// ============================================================
function renderStrategy() {
    if (!strategyData) { showError('No data'); return; }

    // Header
    document.getElementById('strategy-name').textContent = strategyData.name;
    document.getElementById('strategy-timeframe').textContent = strategyData.timeframe;
    document.getElementById('strategy-direction').textContent = strategyData.direction.toUpperCase();
    document.getElementById('strategy-leverage').textContent = `x${strategyData.leverage}`;

    // Params (per strategy type)
    const params = strategyData.params || {};
    let paramsText = '';
    if (params.st_period !== undefined) {
        paramsText = `Period: ${params.st_period}, Multiplier: ${params.st_multiplier}`;
    } else if (params.rsi_period !== undefined) {
        paramsText = `Period: ${params.rsi_period}, OS: ${params.rsi_oversold}, OB: ${params.rsi_overbought}`;
    } else if (params.macd_fast !== undefined) {
        paramsText = `Fast: ${params.macd_fast}, Slow: ${params.macd_slow}, Signal: ${params.macd_signal}`;
    } else {
        paramsText = Object.entries(params).map(([k, v]) => `${k}: ${v}`).join(', ') || 'N/A';
    }
    document.getElementById('strategy-params').textContent = paramsText;

    // Status
    const statusBadge = document.getElementById('strategy-status');
    statusBadge.className = `badge badge-${strategyData.status}`;
    statusBadge.textContent = strategyData.status.toUpperCase();

    // Control buttons
    document.getElementById('start-btn').style.display = strategyData.status === 'running' ? 'none' : 'flex';
    document.getElementById('stop-btn').style.display = strategyData.status === 'running' ? 'flex' : 'none';

    // Statistics
    const s = strategyData.statistics || {};
    renderTopBar(s);
    renderMetricsTables(s);
    renderTrades(strategyData.trades);

    // Show content BEFORE rendering chart so container has real dimensions
    showContent();
    renderEquityCurve(strategyData.equity_curve);
    lucide.createIcons();
}

// ============================================================
// Top summary bar
// ============================================================
function renderTopBar(s) {
    // Total PnL
    const pnlEl = document.getElementById('top-total-pnl');
    pnlEl.innerHTML = formatPnL(s.total_pnl || 0);
    document.getElementById('top-total-pnl-pct').textContent =
        `${s.total_pnl_pct >= 0 ? '+' : ''}${(s.total_pnl_pct || 0).toFixed(2)}%`;

    // Balance
    document.getElementById('top-balance').textContent = `$${(s.current_balance || 1000).toLocaleString('en', {minimumFractionDigits: 2})}`;

    // Total trades
    document.getElementById('top-total-trades').textContent = s.total_trades || 0;
    document.getElementById('top-open-trades').textContent = `Открытых: ${s.open_trades || 0}`;

    // Win rate
    document.getElementById('top-win-rate').textContent = `${(s.win_rate || 0).toFixed(1)}%`;
    document.getElementById('top-win-loss').textContent = `${s.win_count || 0}W / ${s.loss_count || 0}L`;

    // Profit factor
    document.getElementById('top-profit-factor').textContent = fmtPF(s.profit_factor);
    document.getElementById('top-avg-duration').textContent = `Avg: ${s.avg_duration || '-'}`;
}

// ============================================================
// Detailed metrics tables
// ============================================================
function renderMetricsTables(s) {
    // Доходность
    document.getElementById('m-initial-balance').textContent = `$${(s.initial_balance || 1000).toFixed(2)}`;
    document.getElementById('m-net-pnl').innerHTML = formatPnL(s.total_pnl || 0);
    document.getElementById('m-gross-profit').innerHTML = `<span class="pnl-positive">+$${(s.gross_profit || 0).toFixed(2)}</span>`;
    document.getElementById('m-gross-loss').innerHTML = `<span class="pnl-negative">-$${Math.abs(s.gross_loss || 0).toFixed(2)}</span>`;
    document.getElementById('m-total-fees').textContent = `$${(s.total_fees || 0).toFixed(4)}`;
    document.getElementById('m-profit-factor').textContent = fmtPF(s.profit_factor);
    document.getElementById('m-expectancy').innerHTML = formatPnL(s.expectancy || 0);

    // Анализ сделок
    document.getElementById('m-total-trades').textContent = s.total_trades || 0;
    document.getElementById('m-win-count').textContent = s.win_count || 0;
    document.getElementById('m-loss-count').textContent = s.loss_count || 0;
    document.getElementById('m-win-rate').textContent = `${(s.win_rate || 0).toFixed(1)}%`;
    document.getElementById('m-avg-win').innerHTML = `<span class="pnl-positive">+$${Math.abs(s.avg_win || 0).toFixed(4)}</span>`;
    document.getElementById('m-avg-loss').innerHTML = `<span class="pnl-negative">-$${Math.abs(s.avg_loss || 0).toFixed(4)}</span>`;
    document.getElementById('m-best-trade').innerHTML = formatPnL(s.best_trade || 0);
    document.getElementById('m-worst-trade').innerHTML = formatPnL(s.worst_trade || 0);

    // Риск
    document.getElementById('m-max-dd').textContent = `$${(s.max_drawdown || 0).toFixed(2)}`;
    document.getElementById('m-max-dd-pct').textContent = `${(s.max_drawdown_pct || 0).toFixed(2)}%`;
    document.getElementById('m-sharpe').textContent = (s.sharpe_ratio || 0).toFixed(2);
    document.getElementById('m-sl-hits').textContent = s.sl_hits || 0;

    // Серии
    document.getElementById('m-consec-wins').textContent = s.max_consec_wins || 0;
    document.getElementById('m-consec-losses').textContent = s.max_consec_losses || 0;
    document.getElementById('m-avg-duration').textContent = s.avg_duration || '-';
    const bestPct = s.best_trade_pct || 0;
    document.getElementById('m-best-trade-pct').textContent = `${bestPct >= 0 ? '+' : ''}${bestPct.toFixed(2)}%`;
    document.getElementById('m-worst-trade-pct').textContent = `${(s.worst_trade_pct || 0).toFixed(2)}%`;
}

// ============================================================
// Equity Curve (Lightweight Charts)
// ============================================================
function renderEquityCurve(equityData) {
    const container = document.getElementById('equity-chart');
    container.innerHTML = '';

    if (!equityData || equityData.length === 0) {
        container.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--text-muted);">Нет данных для графика</div>';
        return;
    }

    // Check if Lightweight Charts is available
    if (typeof LightweightCharts === 'undefined') {
        container.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--text-muted);">Lightweight Charts не загружен</div>';
        return;
    }

    const chart = LightweightCharts.createChart(container, {
        width: container.clientWidth,
        height: 300,
        layout: {
            background: { type: 'solid', color: 'transparent' },
            textColor: '#94a3b8',
        },
        grid: {
            vertLines: { color: 'rgba(255,255,255,0.03)' },
            horzLines: { color: 'rgba(255,255,255,0.03)' },
        },
        rightPriceScale: { borderColor: 'rgba(255,255,255,0.1)' },
        timeScale: { borderColor: 'rgba(255,255,255,0.1)', timeVisible: true },
        crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
    });

    // Baseline series (green above 1000, red below)
    const series = chart.addBaselineSeries({
        baseValue: { type: 'price', price: 1000 },
        topLineColor: '#00e676',
        topFillColor1: 'rgba(0, 230, 118, 0.2)',
        topFillColor2: 'rgba(0, 230, 118, 0.02)',
        bottomLineColor: '#ff5252',
        bottomFillColor1: 'rgba(255, 82, 82, 0.02)',
        bottomFillColor2: 'rgba(255, 82, 82, 0.2)',
        lineWidth: 2,
    });

    // Convert equity data to chart format
    const chartData = equityData.map(point => ({
        time: Math.floor(new Date(point.time).getTime() / 1000),
        value: point.value
    })).filter(d => !isNaN(d.time));

    if (chartData.length > 0) {
        series.setData(chartData);
        chart.timeScale().fitContent();
    }

    equityChart = chart;

    // Resize handler
    new ResizeObserver(() => {
        chart.applyOptions({ width: container.clientWidth });
    }).observe(container);
}

// ============================================================
// Trade list (TradingView-style)
// ============================================================
function renderTrades(trades) {
    const tbody = document.getElementById('trades-list');
    tbody.innerHTML = '';

    if (!trades || trades.length === 0) {
        tbody.innerHTML = '<tr><td colspan="12" style="text-align:center;padding:2rem;color:var(--text-muted);">Нет сделок</td></tr>';
        return;
    }

    trades.forEach((trade, idx) => {
        const tr = document.createElement('tr');

        // #
        addCell(tr, trades.length - idx);

        // Тип (Long/Short)
        const typeCell = document.createElement('td');
        const typeBadge = document.createElement('span');
        typeBadge.className = `badge badge-${trade.direction}`;
        typeBadge.textContent = trade.direction === 'long' ? 'Длинная' : 'Короткая';
        typeCell.appendChild(typeBadge);
        tr.appendChild(typeCell);

        // Дата открытия
        addCell(tr, fmtDate(trade.opened_at));

        // Дата закрытия
        addCell(tr, trade.closed_at ? fmtDate(trade.closed_at) : '-');

        // Цена входа
        addCell(tr, `$${fmtPrice(trade.entry_price)}`);

        // Цена выхода
        addCell(tr, trade.close_price ? `$${fmtPrice(trade.close_price)}` : '-');

        // Размер позиции
        addCell(tr, trade.qty ? trade.qty.toFixed(6) : '-');

        // PnL
        const pnlCell = document.createElement('td');
        pnlCell.innerHTML = trade.status === 'open' ? '<span class="pnl-neutral">open</span>' : formatPnL(trade.pnl || 0);
        tr.appendChild(pnlCell);

        // PnL %
        const pnlPctCell = document.createElement('td');
        pnlPctCell.innerHTML = trade.pnl_percent ? formatPnLPct(trade.pnl_percent) : '-';
        tr.appendChild(pnlPctCell);

        // Комиссия
        addCell(tr, trade.fees ? `$${trade.fees.toFixed(4)}` : '-');

        // Совокупный PnL
        const cumCell = document.createElement('td');
        cumCell.innerHTML = trade.cumulative_pnl !== undefined ? formatPnL(trade.cumulative_pnl) : '-';
        tr.appendChild(cumCell);

        // Причина
        addCell(tr, trade.close_reason || (trade.status === 'open' ? 'open' : '-'));

        tbody.appendChild(tr);
    });
}

function filterTrades(filter) {
    if (!strategyData || !strategyData.trades) return;
    let filtered = strategyData.trades;
    if (filter === 'wins') filtered = filtered.filter(t => (t.pnl || 0) > 0);
    else if (filter === 'losses') filtered = filtered.filter(t => (t.pnl || 0) < 0);
    else if (filter === 'open') filtered = filtered.filter(t => t.status === 'open');
    renderTrades(filtered);
}

// ============================================================
// Utilities
// ============================================================
function addCell(tr, text) {
    const td = document.createElement('td');
    td.textContent = text;
    tr.appendChild(td);
}

function formatPnL(value) {
    if (value === null || value === undefined || value === 0)
        return '<span class="pnl-neutral">$0.00</span>';
    const sign = value > 0 ? '+' : '-';
    const cls = value > 0 ? 'pnl-positive' : 'pnl-negative';
    return `<span class="${cls}">${sign}$${Math.abs(value).toFixed(2)}</span>`;
}

function formatPnLPct(value) {
    if (!value) return '<span class="pnl-neutral">0.00%</span>';
    const sign = value > 0 ? '+' : '-';
    const cls = value > 0 ? 'pnl-positive' : 'pnl-negative';
    return `<span class="${cls}">${sign}${Math.abs(value).toFixed(2)}%</span>`;
}

function fmtPF(value) {
    if (!value) return '0.00';
    if (value === Infinity || value > 999) return '∞';
    return value.toFixed(2);
}

function fmtDate(dateString) {
    if (!dateString) return '-';
    const d = new Date(dateString);
    return d.toLocaleString('ru-RU', { day: '2-digit', month: 'short', year: '2-digit', hour: '2-digit', minute: '2-digit' });
}

function fmtPrice(price) {
    if (!price) return '0.00';
    if (price >= 1000) return price.toLocaleString('en', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    if (price >= 1) return price.toFixed(2);
    return price.toFixed(6);
}

// ============================================================
// UI States
// ============================================================
function showLoading() {
    document.getElementById('loading-state').style.display = 'block';
    document.getElementById('error-state').style.display = 'none';
    document.getElementById('content-grid').style.display = 'none';
}
function showError(message) {
    document.getElementById('loading-state').style.display = 'none';
    document.getElementById('error-state').style.display = 'block';
    document.getElementById('error-message').textContent = message;
    document.getElementById('content-grid').style.display = 'none';
}
function showContent() {
    document.getElementById('loading-state').style.display = 'none';
    document.getElementById('error-state').style.display = 'none';
    document.getElementById('content-grid').style.display = 'block';
}
