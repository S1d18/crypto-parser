/**
 * Strategies Catalog Page
 *
 * Features:
 * - Load all strategies from /api/strategies/all
 * - Filter by type, coin, TF, direction, category, status, search
 * - Sort by name, PnL, win rate, trades, balance
 * - Pagination (50 per page)
 * - Modal popup with detailed stats from /api/strategies/<id>
 */

// ============================================================
// State
// ============================================================
let allStrategies = [];
let filteredStrategies = [];
let currentPage = 1;
const perPage = 50;
let currentTypeFilter = 'all';
let currentSortField = 'name';
let currentSortDir = 'asc';

// ============================================================
// Strategy Descriptions Knowledge Base
// ============================================================
const STRATEGY_DESCRIPTIONS = {
    supertrend: {
        name: 'Supertrend',
        description: 'Trend-following strategy based on the Supertrend indicator, which uses ATR (Average True Range) to determine trend direction and generate buy/sell signals.',
        buyLogic: 'Enter long when price crosses above the Supertrend line (trend flips bullish). The Supertrend line acts as a dynamic support level.',
        sellLogic: 'Exit long / enter short when price crosses below the Supertrend line (trend flips bearish). The Supertrend line acts as a dynamic resistance level.',
        paramDescriptions: {
            atr_period: 'ATR calculation period',
            atr_multiplier: 'ATR multiplier for band width',
            sl_percent: 'Stop-loss percentage',
            leverage: 'Position leverage',
        }
    },
    rsi: {
        name: 'RSI',
        description: 'Mean-reversion strategy based on the Relative Strength Index (RSI). Identifies overbought/oversold conditions to generate counter-trend signals.',
        buyLogic: 'Enter long when RSI drops below the oversold threshold (e.g., 30), indicating the asset may be undervalued and due for a bounce.',
        sellLogic: 'Exit long / enter short when RSI rises above the overbought threshold (e.g., 70), indicating the asset may be overvalued and due for a pullback.',
        paramDescriptions: {
            rsi_period: 'RSI calculation period',
            overbought: 'Overbought threshold',
            oversold: 'Oversold threshold',
            sl_percent: 'Stop-loss percentage',
        }
    },
    macd: {
        name: 'MACD',
        description: 'Momentum strategy using Moving Average Convergence Divergence (MACD). Detects changes in momentum by comparing two exponential moving averages.',
        buyLogic: 'Enter long when the MACD line crosses above the signal line (bullish crossover), indicating increasing upward momentum.',
        sellLogic: 'Exit long / enter short when the MACD line crosses below the signal line (bearish crossover), indicating increasing downward momentum.',
        paramDescriptions: {
            fast_period: 'Fast EMA period',
            slow_period: 'Slow EMA period',
            signal_period: 'Signal line period',
            sl_percent: 'Stop-loss percentage',
        }
    }
};

// ============================================================
// Initialization
// ============================================================
document.addEventListener('DOMContentLoaded', function() {
    loadStrategies();
    setupFilters();
    setupPagination();

    // Close modal on Escape
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') closeModal();
    });

    // Close modal on overlay click
    document.getElementById('strategy-modal').addEventListener('click', function(e) {
        if (e.target === this) closeModal();
    });
});

// ============================================================
// Data Loading
// ============================================================
async function loadStrategies() {
    showLoading();

    try {
        const response = await fetch('/api/strategies/all');
        const data = await response.json();

        if (data.status === 'ok') {
            allStrategies = data.strategies;
            document.getElementById('strategies-count').textContent = `(${allStrategies.length})`;

            // Populate TF filter dynamically
            populateTFFilter();

            applyFilters();
        } else {
            showEmpty();
        }
    } catch (error) {
        console.error('Error loading strategies:', error);
        showEmpty();
    }
}

function populateTFFilter() {
    const tfs = [...new Set(allStrategies.map(s => s.timeframe))].sort();
    const select = document.getElementById('filter-tf');
    // Keep "All" option, remove the rest
    select.innerHTML = '<option value="all">All</option>';
    tfs.forEach(tf => {
        const opt = document.createElement('option');
        opt.value = tf;
        opt.textContent = tf;
        select.appendChild(opt);
    });
}

// ============================================================
// Filtering & Sorting
// ============================================================
function applyFilters() {
    const search = document.getElementById('filter-search').value.toLowerCase().trim();
    const coin = document.getElementById('filter-coin').value;
    const tf = document.getElementById('filter-tf').value;
    const direction = document.getElementById('filter-direction').value;
    const category = document.getElementById('filter-category').value;
    const status = document.getElementById('filter-status').value;
    const sortVal = document.getElementById('filter-sort').value;

    // Parse sort value
    const parts = sortVal.split('_');
    const sortDir = parts.pop();
    const sortField = parts.join('_');

    filteredStrategies = allStrategies.filter(s => {
        // Type filter (from tabs)
        if (currentTypeFilter !== 'all' && s.type !== currentTypeFilter) return false;

        // Search
        if (search && !s.name.toLowerCase().includes(search)) return false;

        // Coin
        if (coin !== 'all') {
            const sCoin = (s.symbol || '').split('/')[0].replace('USDT', '');
            if (sCoin !== coin) return false;
        }

        // Timeframe
        if (tf !== 'all' && s.timeframe !== tf) return false;

        // Direction
        if (direction !== 'all' && s.direction !== direction) return false;

        // Category
        if (category !== 'all' && s.category !== category) return false;

        // Status
        if (status !== 'all' && s.status !== status) return false;

        return true;
    });

    // Sort
    filteredStrategies.sort((a, b) => {
        let va, vb;
        switch (sortField) {
            case 'name':
                va = a.name.toLowerCase();
                vb = b.name.toLowerCase();
                return sortDir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va);
            case 'pnl':
                va = a.total_pnl || 0;
                vb = b.total_pnl || 0;
                break;
            case 'winrate':
                va = a.win_rate || 0;
                vb = b.win_rate || 0;
                break;
            case 'trades':
                va = a.trades_count || 0;
                vb = b.trades_count || 0;
                break;
            case 'balance':
                va = a.current_balance || 0;
                vb = b.current_balance || 0;
                break;
            default:
                va = a.name.toLowerCase();
                vb = b.name.toLowerCase();
                return va.localeCompare(vb);
        }
        return sortDir === 'asc' ? va - vb : vb - va;
    });

    currentPage = 1;
    updateTabCounts();
    renderSummaryStats();

    if (filteredStrategies.length > 0) {
        renderStrategies();
    } else {
        showEmpty();
    }
}

function setTypeFilter(type) {
    currentTypeFilter = type;

    // Update tab active state
    document.querySelectorAll('#type-tabs .tab').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.type === type);
    });

    applyFilters();
}

function setupFilters() {
    // Search with debounce
    let searchTimeout;
    document.getElementById('filter-search').addEventListener('input', function() {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(applyFilters, 300);
    });

    // Select filters
    ['filter-coin', 'filter-tf', 'filter-direction', 'filter-category', 'filter-status', 'filter-sort'].forEach(id => {
        document.getElementById(id).addEventListener('change', applyFilters);
    });

    // Sortable column headers
    document.querySelectorAll('.sortable').forEach(th => {
        th.addEventListener('click', function() {
            const field = this.dataset.sort;
            const sortSelect = document.getElementById('filter-sort');

            // Determine direction
            if (currentSortField === field) {
                currentSortDir = currentSortDir === 'asc' ? 'desc' : 'asc';
            } else {
                currentSortField = field;
                currentSortDir = field === 'name' ? 'asc' : 'desc';
            }

            // Update sort select to match
            const sortKey = `${field}_${currentSortDir}`;
            for (let i = 0; i < sortSelect.options.length; i++) {
                if (sortSelect.options[i].value === sortKey) {
                    sortSelect.value = sortKey;
                    break;
                }
            }

            // Update visual indicator
            document.querySelectorAll('.sortable').forEach(h => {
                h.classList.remove('sort-asc', 'sort-desc');
            });
            this.classList.add(currentSortDir === 'asc' ? 'sort-asc' : 'sort-desc');

            applyFilters();
        });
    });
}

function setupPagination() {
    document.getElementById('prev-btn').addEventListener('click', () => {
        if (currentPage > 1) { currentPage--; renderStrategies(); }
    });
    document.getElementById('next-btn').addEventListener('click', () => {
        const totalPages = Math.ceil(filteredStrategies.length / perPage);
        if (currentPage < totalPages) { currentPage++; renderStrategies(); }
    });
}

// ============================================================
// Rendering
// ============================================================
function renderStrategies() {
    const tbody = document.getElementById('strategies-list');
    tbody.innerHTML = '';

    const totalPages = Math.ceil(filteredStrategies.length / perPage) || 1;
    if (currentPage > totalPages) currentPage = totalPages;

    const start = (currentPage - 1) * perPage;
    const end = start + perPage;
    const pageItems = filteredStrategies.slice(start, end);

    pageItems.forEach(s => {
        const tr = document.createElement('tr');
        tr.onclick = () => openModal(s.id);

        const coin = (s.symbol || '').split('/')[0].replace('USDT', '') || '?';
        const typeBadge = `<span class="badge-type badge-${s.type}">${s.type}</span>`;
        const dirBadge = `<span class="badge badge-${s.direction}">${s.direction.toUpperCase()}</span>`;
        const statusBadge = `<span class="badge badge-${s.status}">${s.status.toUpperCase()}</span>`;
        const catBadge = `<span class="badge badge-${s.category}">${(s.category || 'paper').toUpperCase()}</span>`;

        // Parse params
        let params = {};
        try {
            params = typeof s.params === 'string' ? JSON.parse(s.params) : (s.params || {});
        } catch(e) { params = {}; }

        const slPct = params.sl_percent != null ? `${params.sl_percent}%` : '-';
        const stParams = params.st_period != null
            ? `ST(${params.st_period}, ${params.st_multiplier})`
            : (params.rsi_period != null ? `RSI(${params.rsi_period})` : (params.fast_period != null ? `MACD(${params.fast_period},${params.slow_period})` : '-'));

        tr.innerHTML = `
            <td><strong>${s.name}</strong></td>
            <td>${typeBadge}</td>
            <td>${coin}</td>
            <td>${s.timeframe}</td>
            <td><span style="font-size:0.8rem; color:var(--text-secondary)">${stParams}</span></td>
            <td>${slPct}</td>
            <td>${dirBadge}</td>
            <td>x${s.leverage}</td>
            <td>${catBadge}</td>
            <td>${statusBadge}</td>
            <td class="text-right">${formatPnL(s.total_pnl)}</td>
            <td class="text-right">${s.win_rate.toFixed(1)}%</td>
            <td class="text-right">${s.trades_count}</td>
            <td class="text-right">${formatPnL(s.current_balance - 1000)}</td>
        `;

        tbody.appendChild(tr);
    });

    // Pagination
    const pagination = document.getElementById('pagination');
    if (filteredStrategies.length > perPage) {
        pagination.style.display = 'block';
        document.getElementById('page-info').textContent = `Page ${currentPage} of ${totalPages} (${filteredStrategies.length} strategies)`;
        document.getElementById('prev-btn').disabled = currentPage <= 1;
        document.getElementById('next-btn').disabled = currentPage >= totalPages;
    } else {
        pagination.style.display = 'none';
    }

    showTable();
}

function renderSummaryStats() {
    const shown = filteredStrategies.length;
    const running = filteredStrategies.filter(s => s.status === 'running').length;
    const totalPnl = filteredStrategies.reduce((sum, s) => sum + (s.total_pnl || 0), 0);
    const totalTrades = filteredStrategies.reduce((sum, s) => sum + (s.trades_count || 0), 0);
    const profitable = filteredStrategies.filter(s => (s.total_pnl || 0) > 0).length;

    // Avg win rate (only from strategies with trades)
    const withTrades = filteredStrategies.filter(s => s.trades_count > 0);
    const avgWinRate = withTrades.length > 0
        ? withTrades.reduce((sum, s) => sum + s.win_rate, 0) / withTrades.length
        : 0;

    document.getElementById('stat-shown').textContent = shown;
    document.getElementById('stat-running').textContent = running;

    const pnlEl = document.getElementById('stat-pnl');
    pnlEl.textContent = `${totalPnl >= 0 ? '+' : ''}$${Math.abs(totalPnl).toFixed(2)}`;
    pnlEl.style.color = totalPnl >= 0 ? 'var(--green)' : 'var(--red)';

    const wrEl = document.getElementById('stat-winrate');
    wrEl.textContent = `${avgWinRate.toFixed(1)}%`;
    wrEl.style.color = avgWinRate >= 50 ? 'var(--green)' : 'var(--red)';

    document.getElementById('stat-trades').textContent = totalTrades;
    document.getElementById('stat-profitable').textContent = `${profitable} / ${shown}`;

    document.getElementById('stats-bar').style.display = 'block';
}

function updateTabCounts() {
    // Count by type across all strategies (not filtered)
    const counts = { all: allStrategies.length };
    allStrategies.forEach(s => {
        counts[s.type] = (counts[s.type] || 0) + 1;
    });

    document.getElementById('tab-all').textContent = counts.all || 0;
    document.getElementById('tab-supertrend').textContent = counts.supertrend || 0;
    document.getElementById('tab-rsi').textContent = counts.rsi || 0;
    document.getElementById('tab-macd').textContent = counts.macd || 0;
}

// ============================================================
// Modal
// ============================================================
async function openModal(strategyId) {
    const modal = document.getElementById('strategy-modal');
    modal.style.display = 'flex';
    document.body.style.overflow = 'hidden';

    // Find basic info from allStrategies
    const strategy = allStrategies.find(s => s.id === strategyId);
    if (strategy) {
        populateModalHeader(strategy);
    }

    // Show loading in body
    document.getElementById('modal-loading').style.display = 'block';
    document.getElementById('modal-description-section').style.display = 'none';
    document.getElementById('modal-params-section').style.display = 'none';
    document.getElementById('modal-metrics-section').style.display = 'none';
    document.getElementById('modal-winloss-section').style.display = 'none';

    // Set detail link
    document.getElementById('modal-detail-link').href = `/strategy/${strategyId}`;

    // Fetch detailed data
    try {
        const response = await fetch(`/api/strategies/${strategyId}`);
        const data = await response.json();

        if (data.status === 'ok') {
            populateModalBody(data, strategy);
        }
    } catch (error) {
        console.error('Error loading strategy details:', error);
    }

    document.getElementById('modal-loading').style.display = 'none';
    lucide.createIcons();
}

function populateModalHeader(strategy) {
    document.getElementById('modal-name').textContent = strategy.name;

    const badges = document.getElementById('modal-badges');
    const coin = (strategy.symbol || '').split('/')[0].replace('USDT', '') || '?';
    badges.innerHTML = `
        <span class="badge-type badge-${strategy.type}">${strategy.type}</span>
        <span class="badge badge-${strategy.status}">${strategy.status.toUpperCase()}</span>
        <span class="badge badge-${strategy.category}">${(strategy.category || 'paper').toUpperCase()}</span>
        <span style="background: var(--bg-tertiary); padding: 0.2rem 0.5rem; border-radius: 4px; font-size: 0.75rem;">${coin}</span>
        <span style="background: var(--bg-tertiary); padding: 0.2rem 0.5rem; border-radius: 4px; font-size: 0.75rem;">${strategy.timeframe}</span>
        <span class="badge badge-${strategy.direction}">${strategy.direction.toUpperCase()}</span>
        <span style="background: var(--bg-tertiary); padding: 0.2rem 0.5rem; border-radius: 4px; font-size: 0.75rem;">x${strategy.leverage}</span>
    `;
}

function populateModalBody(data, strategy) {
    const stats = data.statistics;
    const strategyData = data.strategy;
    const type = strategyData.type;

    // Description
    const desc = STRATEGY_DESCRIPTIONS[type];
    if (desc) {
        const descSection = document.getElementById('modal-description-section');
        descSection.style.display = 'block';
        document.getElementById('modal-description').innerHTML = `
            <p style="margin-bottom: 0.5rem;"><strong>${desc.name}</strong> &mdash; ${desc.description}</p>
            <p style="margin-bottom: 0.25rem; color: var(--green);"><strong>Buy:</strong> ${desc.buyLogic}</p>
            <p style="color: var(--red);"><strong>Sell:</strong> ${desc.sellLogic}</p>
        `;
    }

    // Parameters
    const params = strategyData.params;
    if (params && Object.keys(params).length > 0) {
        const paramsSection = document.getElementById('modal-params-section');
        paramsSection.style.display = 'block';

        const paramDescs = desc ? desc.paramDescriptions : {};
        document.getElementById('modal-params').innerHTML = Object.entries(params).map(([key, val]) => `
            <div class="modal-param-card" title="${paramDescs[key] || key}">
                <div class="modal-param-name">${key}</div>
                <div class="modal-param-value">${val}</div>
            </div>
        `).join('');
    }

    // Performance Metrics
    const metricsSection = document.getElementById('modal-metrics-section');
    metricsSection.style.display = 'block';
    document.getElementById('modal-metrics').innerHTML = `
        <div class="modal-metric-card">
            <div class="modal-metric-label">Total PnL</div>
            <div class="modal-metric-value" style="color: ${stats.total_pnl >= 0 ? 'var(--green)' : 'var(--red)'}">
                ${stats.total_pnl >= 0 ? '+' : ''}$${Math.abs(stats.total_pnl).toFixed(2)}
            </div>
        </div>
        <div class="modal-metric-card">
            <div class="modal-metric-label">Win Rate</div>
            <div class="modal-metric-value" style="color: ${stats.win_rate >= 50 ? 'var(--green)' : 'var(--red)'}">
                ${stats.win_rate.toFixed(1)}%
            </div>
        </div>
        <div class="modal-metric-card">
            <div class="modal-metric-label">Profit Factor</div>
            <div class="modal-metric-value">${stats.profit_factor.toFixed(2)}</div>
        </div>
        <div class="modal-metric-card">
            <div class="modal-metric-label">Sharpe</div>
            <div class="modal-metric-value">${stats.sharpe_ratio.toFixed(2)}</div>
        </div>
        <div class="modal-metric-card">
            <div class="modal-metric-label">Max DD</div>
            <div class="modal-metric-value" style="color: var(--red)">
                -$${Math.abs(stats.max_drawdown).toFixed(2)}
            </div>
        </div>
        <div class="modal-metric-card">
            <div class="modal-metric-label">Expectancy</div>
            <div class="modal-metric-value" style="color: ${stats.expectancy >= 0 ? 'var(--green)' : 'var(--red)'}">
                ${stats.expectancy >= 0 ? '+' : ''}$${Math.abs(stats.expectancy).toFixed(4)}
            </div>
        </div>
        <div class="modal-metric-card">
            <div class="modal-metric-label">Trades</div>
            <div class="modal-metric-value">${stats.total_trades}</div>
        </div>
        <div class="modal-metric-card">
            <div class="modal-metric-label">Avg Duration</div>
            <div class="modal-metric-value">${stats.avg_duration}</div>
        </div>
    `;

    // Win/Loss Analysis Table
    const wlSection = document.getElementById('modal-winloss-section');
    wlSection.style.display = 'block';
    document.getElementById('modal-winloss').innerHTML = `
        <tr><td>Wins / Losses</td><td style="color: var(--green)">${stats.win_count}</td></tr>
        <tr><td>Losses</td><td style="color: var(--red)">${stats.loss_count}</td></tr>
        <tr><td>Avg Win</td><td style="color: var(--green)">+$${Math.abs(stats.avg_win).toFixed(4)}</td></tr>
        <tr><td>Avg Loss</td><td style="color: var(--red)">-$${Math.abs(stats.avg_loss).toFixed(4)}</td></tr>
        <tr><td>Best Trade</td><td style="color: var(--green)">+$${Math.abs(stats.best_trade).toFixed(4)} (${stats.best_trade_pct}%)</td></tr>
        <tr><td>Worst Trade</td><td style="color: var(--red)">-$${Math.abs(stats.worst_trade).toFixed(4)} (${stats.worst_trade_pct}%)</td></tr>
        <tr><td>Max Consec Wins</td><td style="color: var(--green)">${stats.max_consec_wins}</td></tr>
        <tr><td>Max Consec Losses</td><td style="color: var(--red)">${stats.max_consec_losses}</td></tr>
        <tr><td>SL Hits</td><td>${stats.sl_hits}</td></tr>
    `;
}

function closeModal() {
    document.getElementById('strategy-modal').style.display = 'none';
    document.body.style.overflow = '';
}

// ============================================================
// Helpers
// ============================================================
function formatPnL(value) {
    const v = value || 0;
    const cls = v >= 0 ? 'pnl-positive' : 'pnl-negative';
    const sign = v >= 0 ? '+' : '';
    return `<span class="${cls}">${sign}$${Math.abs(v).toFixed(2)}</span>`;
}

function showLoading() {
    document.getElementById('loading-state').style.display = 'block';
    document.getElementById('empty-state').style.display = 'none';
    document.getElementById('strategies-table').style.display = 'none';
    document.getElementById('stats-bar').style.display = 'none';
}

function showEmpty() {
    document.getElementById('loading-state').style.display = 'none';
    document.getElementById('empty-state').style.display = 'block';
    document.getElementById('strategies-table').style.display = 'none';
}

function showTable() {
    document.getElementById('loading-state').style.display = 'none';
    document.getElementById('empty-state').style.display = 'none';
    document.getElementById('strategies-table').style.display = 'table';
}
