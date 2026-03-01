"""
Patch: Add /api/strategies/list (paginated) and rewrite watchlist JS/HTML for server-side pagination.
Run on Pi: python3 patch_watchlist_pagination.py
"""

APP_PATH = '/home/s1d18/crypto_web/api/app.py'
JS_PATH = '/home/s1d18/crypto_web/frontend/static/js/watchlist.js'
HTML_PATH = '/home/s1d18/crypto_web/frontend/templates/watchlist.html'

# ============================================================
# 1. Add /api/strategies/list endpoint to app.py
# ============================================================
NEW_ENDPOINT = r'''
@app.route('/api/strategies/list')
def get_strategies_list():
    """Paginated strategy listing with server-side filters and stats."""
    from core.database import get_database
    from flask import request

    db = get_database()

    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 100, type=int)
    per_page = min(per_page, 200)

    # Filters
    symbol = request.args.get('symbol', '')       # 'BTC', 'ETH', etc.
    category = request.args.get('category', '')    # 'paper', 'live'
    timeframe = request.args.get('timeframe', '')  # '5m', '1h', etc.
    direction = request.args.get('direction', '')   # 'long', 'short', 'both'
    status = request.args.get('status', '')         # 'running', 'stopped'
    group = request.args.get('group', '')           # 'scalping', 'intraday', 'swing', 'position'

    # Sort
    sort_by = request.args.get('sort_by', 'name')
    sort_dir = request.args.get('sort_dir', 'asc')

    # Build WHERE clause for strategies
    where_parts = []
    params = []

    if symbol:
        where_parts.append("s.symbol LIKE ?")
        params.append(f"{symbol.upper()}%")
    if category:
        where_parts.append("s.category = ?")
        params.append(category)
    if timeframe:
        where_parts.append("s.timeframe = ?")
        params.append(timeframe)
    if direction:
        where_parts.append("s.direction = ?")
        params.append(direction)
    if status:
        where_parts.append("s.status = ?")
        params.append(status)

    # Group = timeframe ranges
    if group == 'scalping':
        where_parts.append("s.timeframe IN ('1m','3m','5m','15m')")
    elif group == 'intraday':
        where_parts.append("s.timeframe IN ('30m','1h')")
    elif group == 'swing':
        where_parts.append("s.timeframe IN ('2h','4h','6h')")
    elif group == 'position':
        where_parts.append("s.timeframe IN ('12h','1d')")

    where_clause = " AND ".join(where_parts) if where_parts else "1=1"

    # ---- Summary stats (across ALL filtered strategies, no pagination) ----
    summary_sql = f"""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN s.status = 'running' THEN 1 ELSE 0 END) as running
        FROM strategies s
        WHERE {where_clause}
    """
    summary_row = db.conn.execute(summary_sql, params).fetchone()
    total = summary_row['total'] or 0
    running_count = summary_row['running'] or 0
    total_pages = max(1, (total + per_page - 1) // per_page)

    # Aggregated PnL stats (via trades join)
    pnl_sql = f"""
        SELECT
            COALESCE(SUM(sub.total_pnl), 0) as sum_pnl,
            COALESCE(AVG(sub.total_pnl), 0) as avg_pnl,
            SUM(sub.trades) as sum_trades,
            SUM(sub.wins) as sum_wins,
            SUM(CASE WHEN sub.open_count > 0 THEN 1 ELSE 0 END) as open_pos_count
        FROM (
            SELECT
                s.id,
                COALESCE((SELECT SUM(pnl) FROM trades WHERE strategy_id = s.id AND status = 'closed'), 0) as total_pnl,
                COALESCE((SELECT COUNT(*) FROM trades WHERE strategy_id = s.id AND status = 'closed'), 0) as trades,
                COALESCE((SELECT SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) FROM trades WHERE strategy_id = s.id AND status = 'closed'), 0) as wins,
                COALESCE((SELECT COUNT(*) FROM trades WHERE strategy_id = s.id AND status = 'open'), 0) as open_count
            FROM strategies s
            WHERE {where_clause}
        ) sub
    """
    pnl_row = db.conn.execute(pnl_sql, params).fetchone()
    sum_pnl = round(pnl_row['sum_pnl'] or 0, 2)
    sum_trades = pnl_row['sum_trades'] or 0
    sum_wins = pnl_row['sum_wins'] or 0
    avg_wr = round(sum_wins / sum_trades * 100, 1) if sum_trades > 0 else 0
    open_pos_count = pnl_row['open_pos_count'] or 0

    # Group counts (for tabs)
    group_sql = f"""
        SELECT
            SUM(CASE WHEN s.timeframe IN ('1m','3m','5m','15m') THEN 1 ELSE 0 END) as scalping,
            SUM(CASE WHEN s.timeframe IN ('30m','1h') THEN 1 ELSE 0 END) as intraday,
            SUM(CASE WHEN s.timeframe IN ('2h','4h','6h') THEN 1 ELSE 0 END) as swing,
            SUM(CASE WHEN s.timeframe IN ('12h','1d') THEN 1 ELSE 0 END) as position_g
        FROM strategies s
        WHERE {where_clause.replace("s.timeframe IN " + "('1m','3m','5m','15m')", "1=1").replace("s.timeframe IN " + "('30m','1h')", "1=1").replace("s.timeframe IN " + "('2h','4h','6h')", "1=1").replace("s.timeframe IN " + "('12h','1d')", "1=1")}
    """
    # For group counts, remove the group filter from where
    group_where_parts = [p for p in where_parts if "s.timeframe IN" not in p]
    group_where = " AND ".join(group_where_parts) if group_where_parts else "1=1"
    group_sql2 = f"""
        SELECT
            COUNT(*) as total_all,
            SUM(CASE WHEN s.timeframe IN ('1m','3m','5m','15m') THEN 1 ELSE 0 END) as scalping,
            SUM(CASE WHEN s.timeframe IN ('30m','1h') THEN 1 ELSE 0 END) as intraday,
            SUM(CASE WHEN s.timeframe IN ('2h','4h','6h') THEN 1 ELSE 0 END) as swing,
            SUM(CASE WHEN s.timeframe IN ('12h','1d') THEN 1 ELSE 0 END) as position_g
        FROM strategies s
        WHERE {group_where}
    """
    group_params = [p for i, p in enumerate(params) if "s.timeframe IN" not in (where_parts[i] if i < len(where_parts) else "")]
    # Simpler: just re-build params without group filter
    gp = []
    if symbol:
        gp.append(f"{symbol.upper()}%")
    if category:
        gp.append(category)
    if timeframe:
        gp.append(timeframe)
    if direction:
        gp.append(direction)
    if status:
        gp.append(status)
    # No group param in gp

    # But wait - if timeframe filter is set, group_where still has it
    # Let's just rebuild properly
    gw_parts = []
    gp2 = []
    if symbol:
        gw_parts.append("s.symbol LIKE ?")
        gp2.append(f"{symbol.upper()}%")
    if category:
        gw_parts.append("s.category = ?")
        gp2.append(category)
    if direction:
        gw_parts.append("s.direction = ?")
        gp2.append(direction)
    if status:
        gw_parts.append("s.status = ?")
        gp2.append(status)
    # NO timeframe, NO group for group counts
    gw = " AND ".join(gw_parts) if gw_parts else "1=1"

    group_sql_final = f"""
        SELECT
            COUNT(*) as total_all,
            SUM(CASE WHEN s.timeframe IN ('1m','3m','5m','15m') THEN 1 ELSE 0 END) as scalping,
            SUM(CASE WHEN s.timeframe IN ('30m','1h') THEN 1 ELSE 0 END) as intraday,
            SUM(CASE WHEN s.timeframe IN ('2h','4h','6h') THEN 1 ELSE 0 END) as swing,
            SUM(CASE WHEN s.timeframe IN ('12h','1d') THEN 1 ELSE 0 END) as position_g
        FROM strategies s
        WHERE {gw}
    """
    gr = db.conn.execute(group_sql_final, gp2).fetchone()

    # ---- Sort mapping ----
    sort_map = {
        'name': 's.name',
        'timeframe': 's.timeframe',
        'direction': 's.direction',
        'total_pnl': 'total_pnl',
        'win_rate': 'win_rate',
        'trades_count': 'trades_count',
        'balance': 'current_balance',
    }
    order_col = sort_map.get(sort_by, 's.name')
    order_dir = 'DESC' if sort_dir == 'desc' else 'ASC'

    # ---- Fetch page of strategies with stats ----
    offset = (page - 1) * per_page
    main_sql = f"""
        SELECT
            s.id, s.name, s.type, s.category, s.symbol, s.timeframe,
            s.direction, s.leverage, s.status,
            COALESCE(closed.total_pnl, 0) as total_pnl,
            COALESCE(closed.trades_count, 0) as trades_count,
            COALESCE(closed.wins, 0) as wins,
            CASE WHEN COALESCE(closed.trades_count, 0) > 0
                THEN ROUND(CAST(COALESCE(closed.wins, 0) AS REAL) / closed.trades_count * 100, 1)
                ELSE 0 END as win_rate,
            1000.0 + COALESCE(closed.total_pnl, 0) as current_balance,
            COALESCE(ot.open_count, 0) as open_trades,
            ot.open_side,
            ot.open_entry_price
        FROM strategies s
        LEFT JOIN (
            SELECT
                strategy_id,
                ROUND(SUM(pnl), 4) as total_pnl,
                COUNT(*) as trades_count,
                SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins
            FROM trades WHERE status = 'closed'
            GROUP BY strategy_id
        ) closed ON closed.strategy_id = s.id
        LEFT JOIN (
            SELECT
                strategy_id,
                COUNT(*) as open_count,
                side as open_side,
                entry_price as open_entry_price
            FROM trades WHERE status = 'open'
            GROUP BY strategy_id
        ) ot ON ot.strategy_id = s.id
        WHERE {where_clause}
        ORDER BY {order_col} {order_dir}
        LIMIT ? OFFSET ?
    """

    rows = db.conn.execute(main_sql, params + [per_page, offset]).fetchall()

    strategies = []
    for r in rows:
        strategies.append({
            'id': r['id'],
            'name': r['name'],
            'type': r['type'],
            'category': r['category'],
            'symbol': r['symbol'] or 'BTC/USDT:USDT',
            'timeframe': r['timeframe'],
            'direction': r['direction'],
            'leverage': r['leverage'] or 1,
            'status': r['status'],
            'total_pnl': r['total_pnl'],
            'win_rate': r['win_rate'],
            'trades_count': r['trades_count'],
            'current_balance': round(r['current_balance'], 2),
            'open_trades': r['open_trades'],
            'open_side': r['open_side'],
            'open_entry_price': r['open_entry_price'],
        })

    return jsonify({
        'status': 'ok',
        'page': page,
        'per_page': per_page,
        'total': total,
        'total_pages': total_pages,
        'strategies': strategies,
        'summary': {
            'total': total,
            'running': running_count,
            'open_positions': open_pos_count,
            'sum_pnl': sum_pnl,
            'sum_trades': sum_trades,
            'avg_winrate': avg_wr,
        },
        'group_counts': {
            'all': gr['total_all'] or 0,
            'scalping': gr['scalping'] or 0,
            'intraday': gr['intraday'] or 0,
            'swing': gr['swing'] or 0,
            'position': gr['position_g'] or 0,
        }
    })

'''

with open(APP_PATH, 'r') as f:
    code = f.read()

if '/api/strategies/list' not in code:
    # Insert before create_app
    marker = "# ============================================================\n# Регистрация Blueprints"
    if marker in code:
        code = code.replace(marker, NEW_ENDPOINT + '\n' + marker)
        print("[OK] Added /api/strategies/list endpoint")
    else:
        print("[ERROR] Could not find insertion point!")
else:
    print("[SKIP] /api/strategies/list already exists")

# Add required import at top
if 'from flask import Flask, render_template, jsonify' in code and 'request' not in code.split('\n')[2]:
    # request is already used in other endpoints via local import, no global needed
    pass

with open(APP_PATH, 'w') as f:
    f.write(code)

# ============================================================
# 2. Rewrite watchlist.js
# ============================================================
NEW_JS = r'''/**
 * Watchlist Page — server-side pagination (100 per page)
 */

let currentPage = 1;
const PER_PAGE = 100;
let currentSymbol = null;
let currentGroup = 'all';

document.addEventListener('DOMContentLoaded', function() {
    // Symbol from URL
    const pathParts = window.location.pathname.split('/');
    currentSymbol = pathParts[pathParts.length - 1].toUpperCase();

    loadPage();
    setupFilters();
    setupTabs();
    initWebSocket();

    document.getElementById('refresh-btn').addEventListener('click', () => loadPage());

    document.getElementById('start-all-btn').addEventListener('click', async function() {
        if (!confirm('Start ALL strategies?')) return;
        try {
            const r = await fetch('/api/strategies/start-all', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
            const d = await r.json();
            if (d.status === 'ok') { alert(`Started ${d.count} strategies`); loadPage(); }
        } catch(e) { alert('Error: ' + e.message); }
    });

    document.getElementById('stop-all-btn').addEventListener('click', async function() {
        if (!confirm('Stop ALL strategies?')) return;
        try {
            const r = await fetch('/api/strategies/stop-all', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
            const d = await r.json();
            if (d.status === 'ok') { alert(`Stopped ${d.count} strategies`); loadPage(); }
        } catch(e) { alert('Error: ' + e.message); }
    });

    lucide.createIcons();
});

// ---- Build API URL ----
function buildUrl() {
    const p = new URLSearchParams();
    p.set('page', currentPage);
    p.set('per_page', PER_PAGE);
    if (currentSymbol) p.set('symbol', currentSymbol);
    if (currentGroup && currentGroup !== 'all') p.set('group', currentGroup);

    const cat = document.getElementById('filter-category').value;
    const tf = document.getElementById('filter-timeframe').value;
    const dir = document.getElementById('filter-direction').value;
    const st = document.getElementById('filter-status').value;

    if (cat && cat !== 'all') p.set('category', cat);
    if (tf && tf !== 'all') p.set('timeframe', tf);
    if (dir && dir !== 'all') p.set('direction', dir);
    if (st && st !== 'all') p.set('status', st);

    return `/api/strategies/list?${p.toString()}`;
}

// ---- Load page ----
async function loadPage() {
    showLoading();
    try {
        const resp = await fetch(buildUrl());
        const data = await resp.json();
        if (data.status !== 'ok') { showError('API error'); return; }

        renderStrategies(data.strategies);
        renderSummary(data.summary);
        renderPagination(data.page, data.total_pages, data.total);
        updateTabCounts(data.group_counts);
        updatePageHeader(data.total);

        showTable();
    } catch(e) {
        showError('Failed: ' + e.message);
    }
}

// ---- Filters ----
function setupFilters() {
    ['category','timeframe','direction','status'].forEach(f => {
        const el = document.getElementById(`filter-${f}`);
        if (el) el.addEventListener('change', () => { currentPage = 1; loadPage(); });
    });
}

function setupTabs() {
    document.querySelectorAll('.strategy-tabs .tab').forEach(tab => {
        tab.addEventListener('click', function() {
            document.querySelectorAll('.strategy-tabs .tab').forEach(t => t.classList.remove('active'));
            this.classList.add('active');
            currentGroup = this.dataset.group;
            currentPage = 1;
            loadPage();
        });
    });
}

// ---- Render table ----
function renderStrategies(strategies) {
    const tbody = document.getElementById('strategies-list');
    tbody.innerHTML = '';
    if (!strategies || strategies.length === 0) { showEmpty(); return; }

    strategies.forEach(s => {
        const tr = document.createElement('tr');
        tr.onclick = () => window.location.href = `/strategy/${s.id}`;

        // Name + open badge
        let nameHtml = `<strong>${s.name}</strong>`;
        if (s.open_trades > 0 && s.open_side) {
            const isLong = s.open_side === 'buy';
            const label = isLong ? 'LONG' : 'SHORT';
            const cls = isLong ? 'badge-open-long' : 'badge-open-short';
            const entry = s.open_entry_price ? ` @ $${Number(s.open_entry_price).toLocaleString()}` : '';
            nameHtml += ` <span class="badge ${cls}">${label}${entry}</span>`;
        }

        const catColor = {'live':'rgba(245,158,11,0.2)','paper':'rgba(139,92,246,0.2)'}[s.category] || 'rgba(148,163,184,0.2)';
        const pnlClass = s.total_pnl >= 0 ? 'pnl-positive' : 'pnl-negative';
        const pnlSign = s.total_pnl > 0 ? '+' : '';
        const balClass = s.current_balance >= 1000 ? 'pnl-positive' : 'pnl-negative';

        tr.innerHTML = `
            <td>${nameHtml}</td>
            <td><span class="badge" style="background:${catColor}">${s.category.toUpperCase()}</span></td>
            <td>${s.timeframe}</td>
            <td><span class="badge badge-${s.direction}">${s.direction.toUpperCase()}</span></td>
            <td>x${s.leverage}</td>
            <td class="text-right"><span class="${balClass}">$${s.current_balance.toFixed(2)}</span></td>
            <td><span class="badge badge-${s.status}">${s.status.toUpperCase()}</span></td>
            <td class="text-right"><span class="${pnlClass}">${pnlSign}$${Math.abs(s.total_pnl).toFixed(2)}</span></td>
            <td class="text-right">${s.win_rate.toFixed(1)}%</td>
            <td class="text-right">${s.trades_count}</td>
            <td><button class="btn btn-secondary btn-sm" onclick="event.stopPropagation(); window.location.href='/strategy/${s.id}'"><i data-lucide="eye"></i></button></td>
        `;
        tbody.appendChild(tr);
    });

    lucide.createIcons();
}

// ---- Summary stats ----
function renderSummary(summary) {
    document.getElementById('stat-total').textContent = summary.total;
    document.getElementById('stat-running').textContent = summary.running;
    document.getElementById('stat-open-pos').textContent = summary.open_positions;

    const pnlEl = document.getElementById('stat-pnl');
    const sign = summary.sum_pnl > 0 ? '+' : '';
    const cls = summary.sum_pnl >= 0 ? 'pnl-positive' : 'pnl-negative';
    pnlEl.innerHTML = `<span class="${cls}">${sign}$${Math.abs(summary.sum_pnl).toFixed(2)}</span>`;

    document.getElementById('stat-winrate').textContent = `${summary.avg_winrate}%`;
    document.getElementById('stat-trades').textContent = summary.sum_trades;

    document.getElementById('stats-bar').style.display = 'block';
}

// ---- Pagination ----
function renderPagination(page, totalPages, total) {
    const container = document.getElementById('pagination-controls');
    if (!container) return;

    if (totalPages <= 1) { container.innerHTML = ''; return; }

    let html = `<div class="pagination">`;
    html += `<button class="btn btn-secondary btn-sm" ${page <= 1 ? 'disabled' : ''} onclick="goPage(${page-1})">← Prev</button>`;
    html += `<span class="page-info">Page ${page} / ${totalPages} (${total} strategies)</span>`;
    html += `<button class="btn btn-secondary btn-sm" ${page >= totalPages ? 'disabled' : ''} onclick="goPage(${page+1})">Next →</button>`;
    html += `</div>`;
    container.innerHTML = html;
}

function goPage(p) {
    if (p < 1) return;
    currentPage = p;
    loadPage();
    window.scrollTo({top: 0, behavior: 'smooth'});
}

// ---- Tab counts ----
function updateTabCounts(counts) {
    document.querySelectorAll('.strategy-tabs .tab').forEach(tab => {
        const g = tab.dataset.group;
        if (g && counts[g] !== undefined) {
            const label = g === 'all' ? 'Все' : g.charAt(0).toUpperCase() + g.slice(1);
            tab.textContent = `${label} (${counts[g]})`;
        }
    });
}

function updatePageHeader(total) {
    const h = document.querySelector('.page-header h1');
    const p = document.querySelector('.page-header p');
    if (h && currentSymbol) h.textContent = `${currentSymbol} Watchlist`;
    if (p) p.textContent = `${total} strategies for ${currentSymbol || 'BTC'}`;
}

// ---- WebSocket ----
function initWebSocket() {
    const socket = io();
    socket.on('connect', () => {
        document.getElementById('connection-status').className = 'dot online';
        document.getElementById('connection-text').textContent = 'Connected';
    });
    socket.on('disconnect', () => {
        document.getElementById('connection-status').className = 'dot offline';
        document.getElementById('connection-text').textContent = 'Disconnected';
    });
}

// ---- UI States ----
function showLoading() {
    document.getElementById('loading-state').style.display = 'block';
    document.getElementById('error-state').style.display = 'none';
    document.getElementById('empty-state').style.display = 'none';
    document.getElementById('strategies-table').style.display = 'none';
}
function showError(msg) {
    document.getElementById('loading-state').style.display = 'none';
    document.getElementById('error-state').style.display = 'block';
    document.getElementById('error-message').textContent = msg;
    document.getElementById('strategies-table').style.display = 'none';
}
function showEmpty() {
    document.getElementById('loading-state').style.display = 'none';
    document.getElementById('empty-state').style.display = 'block';
    document.getElementById('strategies-table').style.display = 'none';
}
function showTable() {
    document.getElementById('loading-state').style.display = 'none';
    document.getElementById('error-state').style.display = 'none';
    document.getElementById('empty-state').style.display = 'none';
    document.getElementById('strategies-table').style.display = 'table';
}
'''

with open(JS_PATH, 'w') as f:
    f.write(NEW_JS)
print("[OK] Rewrote watchlist.js with server-side pagination")

# ============================================================
# 3. Update watchlist.html — add pagination div, remove PnL 24h column
# ============================================================
NEW_HTML = r'''{% extends "base.html" %}

{% block title %}Watchlist - Trading Platform{% endblock %}

{% block content %}
<div data-page="watchlist">
    <div class="page-header">
        <h1>{{ symbol or 'BTC' }} Watchlist</h1>
        <p class="text-muted" id="page-subtitle">Loading strategies...</p>
    </div>

    <!-- Group Tabs -->
    <div class="strategy-tabs">
        <button class="tab active" data-group="all">Все (0)</button>
        <button class="tab" data-group="scalping">Scalping (0)</button>
        <button class="tab" data-group="intraday">Intraday (0)</button>
        <button class="tab" data-group="swing">Swing (0)</button>
        <button class="tab" data-group="position">Position (0)</button>
    </div>

    <!-- Filters -->
    <div class="filters-bar">
        <div class="filter-group">
            <label for="filter-category">Category:</label>
            <select id="filter-category">
                <option value="all">All</option>
                <option value="live">Live</option>
                <option value="paper">Paper</option>
            </select>
        </div>
        <div class="filter-group">
            <label for="filter-timeframe">Timeframe:</label>
            <select id="filter-timeframe">
                <option value="all">All</option>
                <option value="1m">1m</option>
                <option value="3m">3m</option>
                <option value="5m">5m</option>
                <option value="15m">15m</option>
                <option value="30m">30m</option>
                <option value="1h">1h</option>
                <option value="2h">2h</option>
                <option value="4h">4h</option>
                <option value="6h">6h</option>
                <option value="12h">12h</option>
                <option value="1d">1d</option>
            </select>
        </div>
        <div class="filter-group">
            <label for="filter-direction">Direction:</label>
            <select id="filter-direction">
                <option value="all">All</option>
                <option value="long">Long</option>
                <option value="short">Short</option>
                <option value="both">Both</option>
            </select>
        </div>
        <div class="filter-group">
            <label for="filter-status">Status:</label>
            <select id="filter-status">
                <option value="all">All</option>
                <option value="running">Running</option>
                <option value="stopped">Stopped</option>
            </select>
        </div>
        <div class="filter-group" style="margin-left: auto; display: flex; gap: 1rem;">
            <button class="btn btn-success" id="start-all-btn"><i data-lucide="play"></i> Start All</button>
            <button class="btn btn-danger" id="stop-all-btn"><i data-lucide="square"></i> Stop All</button>
            <button class="btn btn-secondary" id="refresh-btn"><i data-lucide="refresh-cw"></i> Refresh</button>
        </div>
    </div>

    <!-- Summary Stats -->
    <div id="stats-bar" style="display: none; padding: 0.75rem var(--spacing-xl) 0;">
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 0.75rem;">
            <div class="wl-stat-card">
                <div class="wl-stat-label">Strategies</div>
                <div class="wl-stat-value" id="stat-total">0</div>
            </div>
            <div class="wl-stat-card">
                <div class="wl-stat-label">Running</div>
                <div class="wl-stat-value" id="stat-running" style="color: var(--green);">0</div>
            </div>
            <div class="wl-stat-card">
                <div class="wl-stat-label">Open Pos.</div>
                <div class="wl-stat-value" id="stat-open-pos" style="color: var(--yellow, #f59e0b);">0</div>
            </div>
            <div class="wl-stat-card">
                <div class="wl-stat-label">Total PnL</div>
                <div class="wl-stat-value" id="stat-pnl">$0.00</div>
            </div>
            <div class="wl-stat-card">
                <div class="wl-stat-label">Avg Win Rate</div>
                <div class="wl-stat-value" id="stat-winrate">0%</div>
            </div>
            <div class="wl-stat-card">
                <div class="wl-stat-label">Total Trades</div>
                <div class="wl-stat-value" id="stat-trades">0</div>
            </div>
        </div>
    </div>

    <!-- Table -->
    <div class="table-container">
        <div id="loading-state" style="text-align: center; padding: 3rem; display: block;">
            <i data-lucide="loader" style="width: 48px; height: 48px; animation: spin 1s linear infinite;"></i>
            <p class="text-muted" style="margin-top: 1rem;">Loading strategies...</p>
        </div>
        <div id="error-state" style="text-align: center; padding: 3rem; display: none;">
            <i data-lucide="alert-circle" style="width: 48px; height: 48px; color: var(--red);"></i>
            <p class="text-muted" style="margin-top: 1rem;" id="error-message">Error</p>
            <button class="btn btn-secondary mt-md" onclick="loadPage()">Retry</button>
        </div>
        <div id="empty-state" style="text-align: center; padding: 3rem; display: none;">
            <i data-lucide="inbox" style="width: 48px; height: 48px;"></i>
            <p class="text-muted" style="margin-top: 1rem;">No strategies found</p>
        </div>

        <table id="strategies-table" style="display: none;">
            <thead>
                <tr>
                    <th>Strategy</th>
                    <th>Category</th>
                    <th>TF</th>
                    <th>Direction</th>
                    <th>Leverage</th>
                    <th class="text-right">Balance</th>
                    <th>Status</th>
                    <th class="text-right">Total PnL</th>
                    <th class="text-right">Win Rate</th>
                    <th class="text-right">Trades</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody id="strategies-list"></tbody>
        </table>

        <!-- Pagination -->
        <div id="pagination-controls" style="padding: 1rem var(--spacing-xl);"></div>
    </div>
</div>

<style>
@keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
}
.wl-stat-card {
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 0.6rem 0.75rem;
    text-align: center;
}
.wl-stat-label {
    font-size: 0.7rem;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 0.15rem;
}
.wl-stat-value {
    font-size: 1.1rem;
    font-weight: 700;
}
.badge-open-long {
    display: inline-block;
    background: rgba(34, 197, 94, 0.15);
    color: #22c55e;
    border: 1px solid rgba(34, 197, 94, 0.3);
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.5px;
    margin-left: 8px;
    animation: pulse-green 2s infinite;
}
.badge-open-short {
    display: inline-block;
    background: rgba(239, 68, 68, 0.15);
    color: #ef4444;
    border: 1px solid rgba(239, 68, 68, 0.3);
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.5px;
    margin-left: 8px;
    animation: pulse-red 2s infinite;
}
@keyframes pulse-green {
    0%, 100% { box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.4); }
    50% { box-shadow: 0 0 8px 2px rgba(34, 197, 94, 0.2); }
}
@keyframes pulse-red {
    0%, 100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.4); }
    50% { box-shadow: 0 0 8px 2px rgba(239, 68, 68, 0.2); }
}
.pagination {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 16px;
    padding: 12px 0;
}
.page-info {
    color: var(--text-muted);
    font-size: 14px;
}
</style>
{% endblock %}

{% block extra_js %}
<script src="{{ url_for('static', filename='js/watchlist.js') }}"></script>
{% endblock %}'''

with open(HTML_PATH, 'w') as f:
    f.write(NEW_HTML)
print("[OK] Rewrote watchlist.html with pagination UI")

print("\n[DONE] All patches applied.")
