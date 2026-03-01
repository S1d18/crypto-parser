/**
 * Screener Page - активные торговые сигналы
 */

let allSignals = [];
let filteredSignals = [];
let socket = null;

// ============================================================
// Initialization
// ============================================================
document.addEventListener('DOMContentLoaded', function() {
    console.log('Screener page loaded');

    loadSignals();
    initWebSocket();
    setupFilters();

    // Обработчики кнопок
    document.getElementById('refresh-btn').addEventListener('click', loadSignals);
    document.getElementById('clear-old-btn').addEventListener('click', clearOldSignals);

    // Auto-refresh каждые 30 секунд
    setInterval(loadSignals, 30000);

    lucide.createIcons();
});

// ============================================================
// API Functions
// ============================================================

async function loadSignals() {
    showLoading();

    try {
        // TODO: Создать endpoint /api/signals
        // Временно используем моковые данные
        allSignals = generateMockSignals();

        console.log(`Loaded ${allSignals.length} signals`);
        applyFilters();

    } catch (error) {
        console.error('Error loading signals:', error);
        showEmpty();
    }
}

function generateMockSignals() {
    // Моковые данные для демонстрации
    const now = new Date();
    return [
        {
            id: 1,
            timestamp: new Date(now.getTime() - 5 * 60000).toISOString(),
            strategy_name: 'Supertrend 4h Long',
            symbol: 'BTCUSDT',
            action: 'buy',
            price: 43250.50,
            confidence: 87,
            reason: 'Supertrend UP crossover',
            executed: false
        },
        {
            id: 2,
            timestamp: new Date(now.getTime() - 15 * 60000).toISOString(),
            strategy_name: 'RSI 1h Oversold',
            symbol: 'BTCUSDT',
            action: 'buy',
            price: 43180.00,
            confidence: 65,
            reason: 'RSI < 30',
            executed: true
        },
        {
            id: 3,
            timestamp: new Date(now.getTime() - 25 * 60000).toISOString(),
            strategy_name: 'Supertrend 10m Short',
            symbol: 'BTCUSDT',
            action: 'sell',
            price: 43300.00,
            confidence: 72,
            reason: 'Supertrend DOWN crossover',
            executed: false
        },
    ];
}

async function clearOldSignals() {
    // TODO: Реализовать удаление старых сигналов через API
    const oneHourAgo = new Date(Date.now() - 3600000);
    allSignals = allSignals.filter(s => new Date(s.timestamp) > oneHourAgo);
    applyFilters();
}

// ============================================================
// WebSocket
// ============================================================

function initWebSocket() {
    socket = io();

    socket.on('connect', function() {
        console.log('WebSocket connected');
    });

    socket.on('signal', function(data) {
        console.log('New signal:', data);
        // Добавить новый сигнал в начало
        allSignals.unshift(data);
        applyFilters();
        showNotification('New Signal', `${data.action.toUpperCase()} ${data.symbol}`);
    });
}

// ============================================================
// Filters
// ============================================================

function setupFilters() {
    const filters = ['action', 'confidence', 'executed'];
    filters.forEach(filterName => {
        const element = document.getElementById(`filter-${filterName}`);
        if (element) {
            element.addEventListener('change', applyFilters);
        }
    });
}

function applyFilters() {
    const action = document.getElementById('filter-action').value;
    const confidence = document.getElementById('filter-confidence').value;
    const executed = document.getElementById('filter-executed').value;

    filteredSignals = allSignals.filter(signal => {
        if (action !== 'all' && signal.action !== action) return false;

        if (confidence !== 'all') {
            const conf = signal.confidence || 0;
            if (confidence === 'high' && conf <= 70) return false;
            if (confidence === 'medium' && (conf < 40 || conf > 70)) return false;
            if (confidence === 'low' && conf >= 40) return false;
        }

        if (executed !== 'all' && String(signal.executed) !== executed) return false;

        return true;
    });

    console.log(`Filtered: ${filteredSignals.length} / ${allSignals.length}`);
    renderSignals();
}

// ============================================================
// Rendering
// ============================================================

function renderSignals() {
    const tbody = document.getElementById('signals-list');
    tbody.innerHTML = '';

    if (filteredSignals.length === 0) {
        showEmpty();
        return;
    }

    filteredSignals.forEach(signal => {
        const row = createSignalRow(signal);
        tbody.appendChild(row);
    });

    showTable();
    lucide.createIcons();
}

function createSignalRow(signal) {
    const tr = document.createElement('tr');

    // Время
    const timeCell = document.createElement('td');
    timeCell.textContent = formatTime(signal.timestamp);
    tr.appendChild(timeCell);

    // Стратегия
    const strategyCell = document.createElement('td');
    strategyCell.innerHTML = `<strong>${signal.strategy_name}</strong>`;
    tr.appendChild(strategyCell);

    // Символ
    const symbolCell = document.createElement('td');
    symbolCell.textContent = signal.symbol;
    tr.appendChild(symbolCell);

    // Действие
    const actionCell = document.createElement('td');
    const actionBadge = document.createElement('span');
    actionBadge.className = `badge badge-${signal.action === 'buy' ? 'long' : 'short'}`;
    actionBadge.textContent = signal.action.toUpperCase();
    actionCell.appendChild(actionBadge);
    tr.appendChild(actionCell);

    // Цена
    const priceCell = document.createElement('td');
    priceCell.className = 'text-right';
    priceCell.textContent = `$${signal.price.toFixed(2)}`;
    tr.appendChild(priceCell);

    // Confidence
    const confCell = document.createElement('td');
    confCell.innerHTML = `<span style="color: ${getConfidenceColor(signal.confidence)}">${signal.confidence}%</span>`;
    tr.appendChild(confCell);

    // Причина
    const reasonCell = document.createElement('td');
    reasonCell.textContent = signal.reason;
    reasonCell.style.fontSize = '0.9rem';
    reasonCell.style.color = 'var(--text-secondary)';
    tr.appendChild(reasonCell);

    // Статус
    const statusCell = document.createElement('td');
    const statusBadge = document.createElement('span');
    statusBadge.className = `badge badge-${signal.executed ? 'running' : 'stopped'}`;
    statusBadge.textContent = signal.executed ? 'EXECUTED' : 'PENDING';
    statusCell.appendChild(statusBadge);
    tr.appendChild(statusCell);

    // Действия
    const actionsCell = document.createElement('td');
    if (!signal.executed) {
        const executeBtn = document.createElement('button');
        executeBtn.className = 'btn btn-success btn-sm';
        executeBtn.innerHTML = '<i data-lucide="play"></i> Execute';
        executeBtn.onclick = () => executeSignal(signal.id);
        actionsCell.appendChild(executeBtn);
    }
    tr.appendChild(actionsCell);

    return tr;
}

// ============================================================
// Actions
// ============================================================

async function executeSignal(signalId) {
    if (!confirm('Выполнить этот сигнал?')) return;

    try {
        // TODO: API endpoint для выполнения сигнала
        console.log(`Executing signal ${signalId}`);

        // Обновить статус
        const signal = allSignals.find(s => s.id === signalId);
        if (signal) {
            signal.executed = true;
            applyFilters();
        }

        showNotification('Success', 'Signal executed');
    } catch (error) {
        console.error('Error executing signal:', error);
        alert('Ошибка выполнения сигнала');
    }
}

// ============================================================
// Utilities
// ============================================================

function formatTime(timestamp) {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);

    if (diffMins < 1) return 'Только что';
    if (diffMins < 60) return `${diffMins}m ago`;

    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours}h ago`;

    return date.toLocaleString('ru-RU', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

function getConfidenceColor(confidence) {
    if (confidence >= 70) return 'var(--green)';
    if (confidence >= 40) return 'var(--primary)';
    return 'var(--text-muted)';
}

function showNotification(title, message) {
    console.log(`Notification: ${title} - ${message}`);
    // TODO: реализовать toast notification
}

// ============================================================
// UI States
// ============================================================

function showLoading() {
    document.getElementById('loading-state').style.display = 'block';
    document.getElementById('empty-state').style.display = 'none';
    document.getElementById('signals-table').style.display = 'none';
}

function showEmpty() {
    document.getElementById('loading-state').style.display = 'none';
    document.getElementById('empty-state').style.display = 'block';
    document.getElementById('signals-table').style.display = 'none';
}

function showTable() {
    document.getElementById('loading-state').style.display = 'none';
    document.getElementById('empty-state').style.display = 'none';
    document.getElementById('signals-table').style.display = 'table';
}
