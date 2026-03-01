/**
 * Watchlist Page - Список всех торговых стратегий
 *
 * Функции:
 * - Загрузка стратегий через API
 * - Фильтрация по категории, timeframe, направлению, статусу
 * - Сортировка по колонкам
 * - Real-time обновления через WebSocket
 * - Переход на детальную страницу стратегии
 */

// ============================================================
// State
// ============================================================
let allStrategies = [];
let filteredStrategies = [];
let socket = null;
let currentGroup = 'all';  // Текущая группа (scalping, intraday, swing, position)
let currentSymbol = null;   // Текущая монета (BTC, ETH, SOL, LTC, TON)

// ============================================================
// Initialization
// ============================================================
document.addEventListener('DOMContentLoaded', function() {
    console.log('Watchlist page loaded');

    // Извлечь symbol из URL (/watchlist/btc -> BTC)
    const pathParts = window.location.pathname.split('/');
    currentSymbol = pathParts[pathParts.length - 1].toUpperCase();
    console.log(`Current symbol: ${currentSymbol}`);

    // Загрузить стратегии
    loadStrategies();

    // Инициализация WebSocket
    initWebSocket();

    // Обработчики фильтров и табов
    setupFilters();
    setupTabs();

    // Обработчики кнопок
    document.getElementById('refresh-btn').addEventListener('click', function() {
        loadStrategies();
    });

    document.getElementById('start-all-btn').addEventListener('click', async function() {
        if (!confirm('Запустить ВСЕ стратегии? Это начнет автоматическую торговлю!')) return;

        try {
            const response = await fetch('/api/strategies/start-all', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({})
            });

            if (!response.ok) {
                const text = await response.text();
                console.error('Server error:', response.status, text);
                alert(`Ошибка сервера: ${response.status}`);
                return;
            }

            const data = await response.json();

            if (data.status === 'ok') {
                alert(`Запущено ${data.count} стратегий!`);
                loadStrategies();  // Обновить таблицу
            }
        } catch (error) {
            console.error('Error starting strategies:', error);
            alert('Ошибка запуска стратегий');
        }
    });

    document.getElementById('stop-all-btn').addEventListener('click', async function() {
        if (!confirm('Остановить ВСЕ стратегии?')) return;

        try {
            const response = await fetch('/api/strategies/stop-all', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({})
            });

            if (!response.ok) {
                const text = await response.text();
                console.error('Server error:', response.status, text);
                alert(`Ошибка сервера: ${response.status}`);
                return;
            }

            const data = await response.json();

            if (data.status === 'ok') {
                alert(`Остановлено ${data.count} стратегий`);
                loadStrategies();  // Обновить таблицу
            }
        } catch (error) {
            console.error('Error stopping strategies:', error);
            alert('Ошибка остановки стратегий');
        }
    });

    // Инициализация Lucide icons
    lucide.createIcons();
});

// ============================================================
// API Functions
// ============================================================

/**
 * Загрузить все стратегии (Live + Paper).
 */
async function loadStrategies() {
    showLoading();

    try {
        // Загрузить ВСЕ стратегии из БД (110+ стратегий)
        const response = await fetch('/api/strategies/all');
        const data = await response.json();

        // Обработать стратегии из БД
        allStrategies = [];

        if (data.status === 'ok' && data.strategies) {
            data.strategies.forEach(strategy => {
                allStrategies.push({
                    id: strategy.id,
                    name: strategy.name,
                    category: strategy.category,
                    symbol: strategy.symbol || 'BTC/USDT:USDT',
                    timeframe: strategy.timeframe,
                    direction: strategy.direction,
                    leverage: strategy.leverage || 1,
                    status: strategy.status,
                    type: strategy.type,
                    pnl_24h: strategy.pnl_24h || 0,
                    total_pnl: strategy.total_pnl || 0,
                    win_rate: strategy.win_rate || 0,
                    trades_count: strategy.trades_count || 0,
                    open_trades: strategy.open_trades || 0,
                    initial_balance: strategy.initial_balance || 1000,
                    current_balance: strategy.current_balance || 1000
                });
            });
        }

        console.log(`Loaded ${allStrategies.length} strategies`);

        // Применить фильтры и отобразить
        applyFilters();

    } catch (error) {
        console.error('Error loading strategies:', error);
        showError('Не удалось загрузить стратегии: ' + error.message);
    }
}

/**
 * Загрузить статистику для стратегии.
 */
async function loadStrategyStats(strategyId, category) {
    try {
        let response;
        if (category === 'live') {
            response = await fetch('/api/live/statistics');
        } else if (category === 'paper') {
            response = await fetch(`/api/paper/strategy/${strategyId}`);
        }

        if (response.ok) {
            const data = await response.json();
            return data.statistics || data.statistics;
        }
    } catch (error) {
        console.error(`Error loading stats for ${strategyId}:`, error);
    }
    return null;
}

// ============================================================
// WebSocket
// ============================================================

/**
 * Инициализация WebSocket соединения.
 */
function initWebSocket() {
    socket = io();

    socket.on('connect', function() {
        console.log('WebSocket connected');
        updateConnectionStatus(true);
    });

    socket.on('disconnect', function() {
        console.log('WebSocket disconnected');
        updateConnectionStatus(false);
    });

    socket.on('connection_response', function(data) {
        console.log('Connection response:', data);
    });

    // Обновление сделки
    socket.on('trade_update', function(data) {
        console.log('Trade update:', data);
        // TODO: обновить PnL стратегии в таблице
        loadStrategies();  // Временно - полная перезагрузка
    });

    // Новый сигнал
    socket.on('signal', function(data) {
        console.log('New signal:', data);
        // TODO: показать уведомление
    });

    // Обновление цены
    socket.on('price_update', function(data) {
        console.log('Price update:', data);
        // TODO: обновить текущие цены
    });
}

/**
 * Обновить статус соединения в UI.
 */
function updateConnectionStatus(connected) {
    const dot = document.getElementById('connection-status');
    const text = document.getElementById('connection-text');

    if (connected) {
        dot.classList.remove('offline');
        dot.classList.add('online');
        text.textContent = 'Connected';
    } else {
        dot.classList.remove('online');
        dot.classList.add('offline');
        text.textContent = 'Disconnected';
    }
}

// ============================================================
// Filters
// ============================================================

/**
 * Настроить обработчики фильтров.
 */
function setupFilters() {
    const filters = ['category', 'timeframe', 'direction', 'status'];

    filters.forEach(filterName => {
        const element = document.getElementById(`filter-${filterName}`);
        if (element) {
            element.addEventListener('change', applyFilters);
        }
    });
}

/**
 * Настроить обработчики табов для группировки стратегий.
 */
function setupTabs() {
    const tabs = document.querySelectorAll('.tab');

    tabs.forEach(tab => {
        tab.addEventListener('click', function() {
            // Снять active со всех табов
            tabs.forEach(t => t.classList.remove('active'));

            // Установить active на текущий таб
            this.classList.add('active');

            // Получить группу
            currentGroup = this.dataset.group;

            console.log(`Switched to group: ${currentGroup}`);

            // Применить фильтры
            applyFilters();
        });
    });
}

/**
 * Применить фильтры к списку стратегий.
 */
function applyFilters() {
    const category = document.getElementById('filter-category').value;
    const timeframe = document.getElementById('filter-timeframe').value;
    const direction = document.getElementById('filter-direction').value;
    const status = document.getElementById('filter-status').value;

    filteredStrategies = allStrategies.filter(strategy => {
        // Фильтр по symbol (монета из URL)
        if (currentSymbol) {
            console.log(`DEBUG: strategy.symbol = ${strategy.symbol}, currentSymbol = ${currentSymbol}`);
            const strategyCoin = strategy.symbol.split('/')[0];  // "BTC/USDT:USDT" -> "BTC"
            console.log(`DEBUG: strategyCoin = ${strategyCoin}, match = ${strategyCoin === currentSymbol}`);
            if (strategyCoin !== currentSymbol) return false;
        }

        // Фильтр по группе (из табов)
        if (currentGroup !== 'all') {
            const strategyGroup = getStrategyGroup(strategy.timeframe);
            if (strategyGroup !== currentGroup) return false;
        }

        // Остальные фильтры
        if (category !== 'all' && strategy.category !== category) return false;
        if (timeframe !== 'all' && strategy.timeframe !== timeframe) return false;
        if (direction !== 'all' && strategy.direction !== direction) return false;
        if (status !== 'all' && strategy.status !== status) return false;
        return true;
    });

    console.log(`Filtered: ${filteredStrategies.length} / ${allStrategies.length} (group: ${currentGroup}, symbol: ${currentSymbol})`);

    // Обновить заголовок страницы
    updatePageHeader();

    renderStrategies();
    renderSummaryStats();
}

/**
 * Обновить заголовок страницы с актуальным количеством стратегий.
 */
function updatePageHeader() {
    const headerElement = document.querySelector('.page-header h1');
    const subtitleElement = document.querySelector('.page-header p');

    if (headerElement && currentSymbol) {
        headerElement.textContent = `${currentSymbol} Watchlist`;
    }

    if (subtitleElement) {
        subtitleElement.textContent = `${filteredStrategies.length} стратегий для ${currentSymbol || 'BTC'}`;
    }

    // Обновить счётчики на табах групп
    updateTabCounts();
}

/**
 * Обновить счётчики на табах групп по текущему символу.
 */
function updateTabCounts() {
    // Базовый набор — стратегии текущей монеты
    const coinStrategies = allStrategies.filter(s => {
        if (!currentSymbol) return true;
        const coin = s.symbol.split('/')[0];
        return coin === currentSymbol;
    });

    const counts = { all: coinStrategies.length, scalping: 0, intraday: 0, swing: 0, position: 0 };
    coinStrategies.forEach(s => {
        const g = getStrategyGroup(s.timeframe);
        if (counts[g] !== undefined) counts[g]++;
    });

    document.querySelectorAll('.strategy-tabs .tab').forEach(tab => {
        const group = tab.dataset.group;
        if (group && counts[group] !== undefined) {
            const label = group === 'all' ? 'Все' : group.charAt(0).toUpperCase() + group.slice(1);
            tab.textContent = `${label} (${counts[group]})`;
        }
    });
}

/**
 * Определить группу стратегии по таймфрейму.
 */
function getStrategyGroup(timeframe) {
    if (['1m', '3m', '5m', '15m'].includes(timeframe)) return 'scalping';
    if (['30m', '1h'].includes(timeframe)) return 'intraday';
    if (['2h', '4h', '6h'].includes(timeframe)) return 'swing';
    if (['12h', '1d'].includes(timeframe)) return 'position';
    return 'other';
}

// ============================================================
// Rendering
// ============================================================

/**
 * Отобразить стратегии в таблице.
 */
function renderStrategies() {
    const tbody = document.getElementById('strategies-list');
    tbody.innerHTML = '';

    if (filteredStrategies.length === 0) {
        showEmpty();
        return;
    }

    filteredStrategies.forEach(strategy => {
        const row = createStrategyRow(strategy);
        tbody.appendChild(row);
    });

    showTable();

    // Обновить иконки
    lucide.createIcons();
}

/**
 * Создать строку таблицы для стратегии.
 */
function createStrategyRow(strategy) {
    const tr = document.createElement('tr');
    tr.onclick = () => goToStrategy(strategy.id, strategy.category);

    // Название
    const nameCell = document.createElement('td');
    nameCell.innerHTML = `<strong>${strategy.name}</strong>`;
    tr.appendChild(nameCell);

    // Категория
    const categoryCell = document.createElement('td');
    const categoryBadge = document.createElement('span');
    categoryBadge.className = 'badge';
    categoryBadge.textContent = strategy.category.toUpperCase();
    categoryBadge.style.background = getCategoryColor(strategy.category);
    categoryCell.appendChild(categoryBadge);
    tr.appendChild(categoryCell);

    // Timeframe
    const tfCell = document.createElement('td');
    tfCell.textContent = strategy.timeframe;
    tr.appendChild(tfCell);

    // Направление
    const dirCell = document.createElement('td');
    const dirBadge = document.createElement('span');
    dirBadge.className = `badge badge-${strategy.direction}`;
    dirBadge.textContent = strategy.direction.toUpperCase();
    dirCell.appendChild(dirBadge);
    tr.appendChild(dirCell);

    // Leverage
    const levCell = document.createElement('td');
    levCell.textContent = `x${strategy.leverage}`;
    tr.appendChild(levCell);

    // Баланс = начальный (1000) + total PnL
    const balanceCell = document.createElement('td');
    balanceCell.className = 'text-right';
    const balance = strategy.current_balance;
    const balanceClass = balance >= strategy.initial_balance ? 'pnl-positive' : 'pnl-negative';
    balanceCell.innerHTML = `<span class="${balanceClass}">$${balance.toFixed(2)}</span>`;
    tr.appendChild(balanceCell);

    // Статус
    const statusCell = document.createElement('td');
    const statusBadge = document.createElement('span');
    statusBadge.className = `badge badge-${strategy.status}`;
    statusBadge.textContent = strategy.status.toUpperCase();
    statusCell.appendChild(statusBadge);
    tr.appendChild(statusCell);

    // PnL 24h
    const pnl24hCell = document.createElement('td');
    pnl24hCell.className = 'text-right';
    pnl24hCell.innerHTML = formatPnL(strategy.pnl_24h);
    tr.appendChild(pnl24hCell);

    // Total PnL
    const totalPnlCell = document.createElement('td');
    totalPnlCell.className = 'text-right';
    totalPnlCell.innerHTML = formatPnL(strategy.total_pnl);
    tr.appendChild(totalPnlCell);

    // Win Rate
    const winRateCell = document.createElement('td');
    winRateCell.className = 'text-right';
    winRateCell.textContent = `${strategy.win_rate.toFixed(1)}%`;
    tr.appendChild(winRateCell);

    // Сделок
    const tradesCell = document.createElement('td');
    tradesCell.className = 'text-right';
    tradesCell.textContent = strategy.trades_count;
    tr.appendChild(tradesCell);

    // Действия
    const actionsCell = document.createElement('td');
    actionsCell.onclick = (e) => e.stopPropagation();

    const viewBtn = document.createElement('button');
    viewBtn.className = 'btn btn-secondary btn-sm';
    viewBtn.innerHTML = '<i data-lucide="eye"></i>';
    viewBtn.onclick = () => goToStrategy(strategy.id, strategy.category);
    actionsCell.appendChild(viewBtn);

    tr.appendChild(actionsCell);

    return tr;
}

/**
 * Отобразить сводную статистику.
 */
function renderSummaryStats() {
    const total = filteredStrategies.length;
    const running = filteredStrategies.filter(s => s.status === 'running').length;
    const totalPnl = filteredStrategies.reduce((sum, s) => sum + (s.total_pnl || 0), 0);
    const totalPnl24 = filteredStrategies.reduce((sum, s) => sum + (s.pnl_24h || 0), 0);
    const totalTrades = filteredStrategies.reduce((sum, s) => sum + (s.trades_count || 0), 0);

    // Средний win rate (только стратегии с трейдами)
    const withTrades = filteredStrategies.filter(s => s.trades_count > 0);
    const avgWinRate = withTrades.length > 0
        ? withTrades.reduce((sum, s) => sum + (s.win_rate || 0), 0) / withTrades.length
        : 0;

    // Лучшая и худшая стратегия по total_pnl
    let bestName = '-', worstName = '-';
    if (filteredStrategies.length > 0) {
        const sorted = [...filteredStrategies].sort((a, b) => (b.total_pnl || 0) - (a.total_pnl || 0));
        const best = sorted[0];
        const worst = sorted[sorted.length - 1];
        if (best && best.total_pnl > 0) bestName = `${best.name.split('_').slice(0, 3).join('_')} +$${best.total_pnl.toFixed(2)}`;
        if (worst && worst.total_pnl < 0) worstName = `${worst.name.split('_').slice(0, 3).join('_')} -$${Math.abs(worst.total_pnl).toFixed(2)}`;
    }

    document.getElementById('stat-total').textContent = total;
    document.getElementById('stat-running').textContent = running;
    document.getElementById('stat-pnl').innerHTML = formatPnL(totalPnl);
    document.getElementById('stat-pnl24').innerHTML = formatPnL(totalPnl24);
    document.getElementById('stat-winrate').textContent = `${avgWinRate.toFixed(1)}%`;
    document.getElementById('stat-trades').textContent = totalTrades;
    document.getElementById('stat-best').textContent = bestName;
    document.getElementById('stat-worst').textContent = worstName;

    document.getElementById('stats-bar').style.display = 'block';
}

// ============================================================
// Utilities
// ============================================================

/**
 * Форматировать PnL с цветом.
 */
function formatPnL(value) {
    if (!value || value === 0) {
        return '<span class="pnl-neutral">$0.00</span>';
    }

    const sign = value > 0 ? '+' : '';
    const className = value > 0 ? 'pnl-positive' : 'pnl-negative';
    return `<span class="${className}">${sign}$${Math.abs(value).toFixed(2)}</span>`;
}

/**
 * Получить цвет для категории.
 */
function getCategoryColor(category) {
    const colors = {
        'live': 'rgba(245, 158, 11, 0.2)',
        'paper': 'rgba(139, 92, 246, 0.2)',
        'arbitrage': 'rgba(68, 138, 255, 0.2)'
    };
    return colors[category] || 'rgba(148, 163, 184, 0.2)';
}

/**
 * Перейти на страницу стратегии.
 */
function goToStrategy(strategyId, category) {
    // TODO: использовать реальный ID из БД
    window.location.href = `/strategy/${strategyId}`;
}

// ============================================================
// UI States
// ============================================================

function showLoading() {
    document.getElementById('loading-state').style.display = 'block';
    document.getElementById('error-state').style.display = 'none';
    document.getElementById('empty-state').style.display = 'none';
    document.getElementById('strategies-table').style.display = 'none';
    document.getElementById('stats-bar').style.display = 'none';
}

function showError(message) {
    document.getElementById('loading-state').style.display = 'none';
    document.getElementById('error-state').style.display = 'block';
    document.getElementById('error-message').textContent = message;
    document.getElementById('empty-state').style.display = 'none';
    document.getElementById('strategies-table').style.display = 'none';
    document.getElementById('stats-bar').style.display = 'none';
}

function showEmpty() {
    document.getElementById('loading-state').style.display = 'none';
    document.getElementById('error-state').style.display = 'none';
    document.getElementById('empty-state').style.display = 'block';
    document.getElementById('strategies-table').style.display = 'none';
    document.getElementById('stats-bar').style.display = 'none';
}

function showTable() {
    document.getElementById('loading-state').style.display = 'none';
    document.getElementById('error-state').style.display = 'none';
    document.getElementById('empty-state').style.display = 'none';
    document.getElementById('strategies-table').style.display = 'table';
}
