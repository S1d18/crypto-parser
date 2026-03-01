// Dashboard Real-time Updates
const API_BASE = '';
const UPDATE_INTERVAL = 5000; // 5 секунд

// Утилиты для форматирования
function formatNumber(num, decimals = 2) {
    return parseFloat(num).toFixed(decimals);
}

function formatPrice(price) {
    return `$${formatNumber(price, 2)}`;
}

function formatPnL(pnl) {
    const sign = pnl >= 0 ? '+' : '';
    return `${sign}${formatPrice(pnl)}`;
}

function formatPercent(percent) {
    const sign = percent >= 0 ? '+' : '';
    return `${sign}${formatNumber(percent, 2)}%`;
}

function formatTimestamp(timestamp) {
    const date = new Date(timestamp);
    const now = new Date();
    const diff = Math.floor((now - date) / 1000); // секунды

    if (diff < 60) return `${diff}с назад`;
    if (diff < 3600) return `${Math.floor(diff / 60)}м назад`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}ч назад`;

    const options = {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    };
    return date.toLocaleDateString('ru-RU', options);
}

function formatDuration(openedAt, closedAt = null) {
    const start = new Date(openedAt);
    const end = closedAt ? new Date(closedAt) : new Date();
    const diff = Math.floor((end - start) / 1000); // секунды

    if (diff < 60) return `${diff}с`;
    if (diff < 3600) return `${Math.floor(diff / 60)}м`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}ч ${Math.floor((diff % 3600) / 60)}м`;
    return `${Math.floor(diff / 86400)}д ${Math.floor((diff % 86400) / 3600)}ч`;
}

// Обновление часов
function updateClock() {
    const now = new Date();
    const time = now.toLocaleTimeString('ru-RU', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false
    });
    document.getElementById('clock').textContent = time;
}

// Обновление статуса бота
async function updateBotStatus() {
    try {
        const response = await fetch(`${API_BASE}/api/status`);
        const data = await response.json();

        const statusEl = document.getElementById('bot-status');
        const dotEl = statusEl.querySelector('.status-dot');
        const textEl = statusEl.querySelector('.status-text');

        if (data.bot_running) {
            dotEl.className = 'status-dot status-online';
            textEl.textContent = 'Бот работает';
        } else {
            dotEl.className = 'status-dot status-offline';
            textEl.textContent = 'Бот остановлен';
        }

        // Обновляем позиции
        updatePositions(data.positions);

    } catch (error) {
        console.error('Ошибка получения статуса:', error);
        const statusEl = document.getElementById('bot-status');
        const dotEl = statusEl.querySelector('.status-dot');
        const textEl = statusEl.querySelector('.status-text');
        dotEl.className = 'status-dot status-offline';
        textEl.textContent = 'Ошибка связи';
    }
}

// Обновление позиций
function updatePositions(positions) {
    // Проверяем позицию 4h
    const pos4h = positions.find(p => p.timeframe === '4h');
    updatePosition('4h', pos4h);

    // Проверяем позицию 10m
    const pos10m = positions.find(p => p.timeframe === '10m');
    updatePosition('10m', pos10m);
}

function updatePosition(timeframe, position) {
    const emptyEl = document.getElementById(`empty-${timeframe}`);
    const activeEl = document.getElementById(`active-${timeframe}`);

    if (!position) {
        emptyEl.style.display = 'flex';
        activeEl.style.display = 'none';
        return;
    }

    emptyEl.style.display = 'none';
    activeEl.style.display = 'block';

    // Обновляем данные позиции
    document.getElementById(`entry-${timeframe}`).textContent = formatPrice(position.entry_price);
    document.getElementById(`current-${timeframe}`).textContent = formatPrice(position.entry_price); // TODO: получать текущую цену
    document.getElementById(`sl-${timeframe}`).textContent = formatPrice(position.sl_price);

    // Рассчитываем PnL (примерно, без текущей цены)
    const pnl = 0; // TODO: рассчитать реальный PnL
    const pnlPct = 0;

    const pnlEl = document.getElementById(`pnl-${timeframe}`);
    pnlEl.textContent = `${formatPnL(pnl)} (${formatPercent(pnlPct)})`;
    pnlEl.className = pnl >= 0 ? 'metric-value text-green' : 'metric-value text-red';

    // Обновляем progress bar
    const slPct = timeframe === '4h' ? -3 : -1;
    const progress = (pnlPct / slPct) * 100;
    const progressEl = document.getElementById(`progress-${timeframe}`);
    progressEl.style.width = `${Math.min(Math.max(progress, 0), 100)}%`;

    if (pnlPct < 0) {
        progressEl.style.background = 'var(--gradient-red)';
        progressEl.style.boxShadow = 'var(--shadow-glow-red)';
    }

    document.getElementById(`progress-label-${timeframe}`).textContent = formatPercent(pnlPct);

    // Время открытия
    document.getElementById(`time-${timeframe}`).textContent = `Открыта: ${formatTimestamp(position.opened_at)}`;
}

// Обновление статистики
async function updateStatistics() {
    try {
        const response = await fetch(`${API_BASE}/api/statistics`);
        const data = await response.json();

        // Общая прибыль
        const totalPnlEl = document.getElementById('total-pnl');
        totalPnlEl.textContent = formatPnL(data.total_pnl);
        if (data.total_pnl < 0) {
            totalPnlEl.classList.remove('gradient-text');
            totalPnlEl.classList.add('text-red');
        } else {
            totalPnlEl.classList.add('gradient-text');
            totalPnlEl.classList.remove('text-red');
        }

        document.getElementById('pnl-change').textContent = `${data.total_trades} сделок`;

        // Винрейт
        document.getElementById('win-rate').textContent = `${formatNumber(data.win_rate, 1)}%`;
        document.getElementById('win-stats').textContent =
            `${data.profitable_trades} побед / ${data.losing_trades} убытков`;

        // Всего сделок
        document.getElementById('total-trades').textContent = data.total_trades;
        document.getElementById('avg-pnl').textContent = `Среднее: ${formatPnL(data.avg_trade)}`;

        // Лучшая/худшая сделка
        document.getElementById('best-trade').textContent = formatPnL(data.best_trade);
        document.getElementById('worst-trade').textContent = `Худшая: ${formatPnL(data.worst_trade)}`;

    } catch (error) {
        console.error('Ошибка получения статистики:', error);
    }
}

// Обновление таблицы сделок
async function updateTrades() {
    const limit = document.getElementById('filter-limit').value;
    const timeframe = document.getElementById('filter-timeframe').value;

    try {
        const params = new URLSearchParams({ limit });
        if (timeframe) params.append('timeframe', timeframe);

        const response = await fetch(`${API_BASE}/api/trades?${params}`);
        const trades = await response.json();

        const tbody = document.getElementById('trades-tbody');

        if (trades.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="8" class="loading">
                        <i data-lucide="inbox" class="empty-icon"></i>
                        <p>Нет сделок</p>
                    </td>
                </tr>
            `;
            lucide.createIcons();
            return;
        }

        tbody.innerHTML = trades.map(trade => {
            const pnlClass = trade.pnl >= 0 ? 'text-green' : 'text-red';
            const typeClass = trade.direction === 'long' ? 'badge-long' : 'badge-short';
            const typeText = trade.direction === 'long' ? 'LONG ▲' : 'SHORT ▼';

            let resultBadge = '';
            if (trade.status === 'closed') {
                if (trade.close_reason === 'signal') {
                    resultBadge = '<span class="badge badge-signal">Сигнал</span>';
                } else if (trade.close_reason === 'sl_hit') {
                    resultBadge = '<span class="badge badge-sl">Stop Loss</span>';
                }
            } else {
                resultBadge = '<span class="badge badge-closed">Открыта</span>';
            }

            const duration = formatDuration(trade.opened_at, trade.closed_at);

            return `
                <tr>
                    <td>${formatTimestamp(trade.opened_at)}</td>
                    <td>${trade.timeframe} ${trade.direction === 'long' ? 'Long' : 'Short'}</td>
                    <td><span class="badge ${typeClass}">${typeText}</span></td>
                    <td class="num">${formatPrice(trade.entry_price)}</td>
                    <td class="num">${trade.close_price ? formatPrice(trade.close_price) : '—'}</td>
                    <td class="num ${pnlClass}">${formatPnL(trade.pnl)}</td>
                    <td>${resultBadge}</td>
                    <td class="text-muted">${duration}</td>
                </tr>
            `;
        }).join('');

    } catch (error) {
        console.error('Ошибка получения сделок:', error);
        document.getElementById('trades-tbody').innerHTML = `
            <tr>
                <td colspan="8" class="loading text-red">
                    <i data-lucide="alert-circle"></i>
                    Ошибка загрузки сделок
                </td>
            </tr>
        `;
        lucide.createIcons();
    }
}

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', async () => {
    console.log('Dashboard загружен');

    // Запускаем часы
    updateClock();
    setInterval(updateClock, 1000);

    // Первоначальная загрузка данных
    await Promise.all([
        updateBotStatus(),
        updateStatistics(),
        updateTrades()
    ]);

    // Автообновление каждые 5 секунд
    setInterval(async () => {
        await Promise.all([
            updateBotStatus(),
            updateStatistics()
        ]);
    }, UPDATE_INTERVAL);

    // Слушатели для фильтров
    document.getElementById('filter-limit').addEventListener('change', updateTrades);
    document.getElementById('filter-timeframe').addEventListener('change', updateTrades);

    console.log('Real-time обновление запущено');
});
