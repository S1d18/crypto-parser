/**
 * Lightweight Charts Integration
 *
 * Обёртка для TradingView Lightweight Charts библиотеки.
 * Создаёт профессиональные торговые графики с:
 * - Candlestick/Line series
 * - Trade markers (buy/sell)
 * - Indicator overlays (Supertrend, EMA, etc.)
 * - Real-time updates
 *
 * ВАЖНО: Требуется библиотека lightweight-charts.standalone.production.js
 * Скачать: https://unpkg.com/lightweight-charts@latest/dist/lightweight-charts.standalone.production.js
 * Сохранить в: frontend/static/vendor/
 */

/**
 * Класс для управления торговым графиком.
 */
class TradingChart {
    /**
     * @param {string} containerId - ID контейнера для графика
     * @param {Object} options - Опции графика
     */
    constructor(containerId, options = {}) {
        this.container = document.getElementById(containerId);
        if (!this.container) {
            throw new Error(`Container with id '${containerId}' not found`);
        }

        // Проверить что Lightweight Charts загружен
        if (typeof LightweightCharts === 'undefined') {
            console.error('Lightweight Charts library not loaded!');
            this.showError('Lightweight Charts library not found. Please download it.');
            return;
        }

        this.options = {
            width: this.container.clientWidth,
            height: options.height || 400,
            layout: {
                background: { color: '#0F172A' },
                textColor: '#F8FAFC',
            },
            grid: {
                vertLines: { color: '#1E293B' },
                horzLines: { color: '#1E293B' },
            },
            crosshair: {
                mode: LightweightCharts.CrosshairMode.Normal,
                vertLine: {
                    color: '#475569',
                    width: 1,
                    style: LightweightCharts.LineStyle.Dashed,
                },
                horzLine: {
                    color: '#475569',
                    width: 1,
                    style: LightweightCharts.LineStyle.Dashed,
                },
            },
            timeScale: {
                borderColor: '#475569',
                timeVisible: true,
                secondsVisible: false,
            },
            rightPriceScale: {
                borderColor: '#475569',
            },
            ...options
        };

        this.chart = LightweightCharts.createChart(this.container, this.options);
        this.series = {};
        this.data = {};

        // Адаптивность
        this.setupResizeHandler();
    }

    /**
     * Создать candlestick серию.
     */
    createCandlestickSeries() {
        this.series.candlestick = this.chart.addCandlestickSeries({
            upColor: '#00e676',
            downColor: '#ff5252',
            borderVisible: false,
            wickUpColor: '#00e676',
            wickDownColor: '#ff5252',
        });
        return this.series.candlestick;
    }

    /**
     * Создать line серию для индикаторов.
     * @param {string} name - Имя серии
     * @param {Object} options - Опции (color, lineWidth, lineStyle)
     */
    createLineSeries(name, options = {}) {
        this.series[name] = this.chart.addLineSeries({
            color: options.color || '#F59E0B',
            lineWidth: options.lineWidth || 2,
            lineStyle: options.lineStyle || LightweightCharts.LineStyle.Solid,
            ...options
        });
        return this.series[name];
    }

    /**
     * Установить OHLCV данные.
     * @param {Array} ohlcv - Массив свечей [[time, open, high, low, close, volume], ...]
     */
    setOHLCVData(ohlcv) {
        if (!this.series.candlestick) {
            this.createCandlestickSeries();
        }

        const candleData = ohlcv.map(candle => ({
            time: Math.floor(candle[0] / 1000), // timestamp в секундах
            open: candle[1],
            high: candle[2],
            low: candle[3],
            close: candle[4],
        }));

        this.data.ohlcv = candleData;
        this.series.candlestick.setData(candleData);
    }

    /**
     * Установить данные индикатора.
     * @param {string} name - Имя индикатора (supertrend, ema, etc.)
     * @param {Array} data - Данные [{time, value}, ...]
     */
    setIndicatorData(name, data) {
        if (!this.series[name]) {
            console.warn(`Series '${name}' not created. Creating default line series.`);
            this.createLineSeries(name);
        }

        this.data[name] = data;
        this.series[name].setData(data);
    }

    /**
     * Добавить маркеры сделок.
     * @param {Array} trades - Массив сделок с полями: time, side, price, pnl
     */
    addTradeMarkers(trades) {
        if (!this.series.candlestick) {
            console.error('Candlestick series not created');
            return;
        }

        const markers = trades.map(trade => {
            const isBuy = trade.side === 'buy' || trade.side === 'long';
            const isProfit = (trade.pnl || 0) > 0;

            return {
                time: Math.floor(new Date(trade.time).getTime() / 1000),
                position: isBuy ? 'belowBar' : 'aboveBar',
                color: isBuy ? '#00e676' : '#ff5252',
                shape: isBuy ? 'arrowUp' : 'arrowDown',
                text: trade.pnl ? `${isProfit ? '+' : ''}$${trade.pnl.toFixed(2)}` : '',
            };
        });

        this.series.candlestick.setMarkers(markers);
    }

    /**
     * Обновить последний бар (для real-time).
     * @param {Object} bar - {time, open, high, low, close}
     */
    updateBar(bar) {
        if (!this.series.candlestick) return;

        this.series.candlestick.update({
            time: Math.floor(bar.time / 1000),
            open: bar.open,
            high: bar.high,
            low: bar.low,
            close: bar.close,
        });
    }

    /**
     * Настроить автоматическое изменение размера.
     */
    setupResizeHandler() {
        const resizeObserver = new ResizeObserver(entries => {
            if (entries.length === 0 || entries[0].target !== this.container) return;
            const newRect = entries[0].contentRect;
            this.chart.applyOptions({ width: newRect.width });
        });

        resizeObserver.observe(this.container);
    }

    /**
     * Показать ошибку в контейнере.
     */
    showError(message) {
        this.container.innerHTML = `
            <div style="display: flex; align-items: center; justify-content: center; height: 100%; color: var(--text-muted);">
                <div style="text-align: center;">
                    <i data-lucide="alert-circle" style="width: 48px; height: 48px; margin-bottom: 1rem; color: var(--red);"></i>
                    <p>${message}</p>
                </div>
            </div>
        `;
    }

    /**
     * Очистить график.
     */
    clear() {
        Object.keys(this.series).forEach(key => {
            this.chart.removeSeries(this.series[key]);
        });
        this.series = {};
        this.data = {};
    }

    /**
     * Уничтожить график.
     */
    destroy() {
        this.chart.remove();
    }
}

/**
 * Создать equity curve chart (кумулятивный PnL).
 */
class EquityCurveChart {
    constructor(containerId, options = {}) {
        this.container = document.getElementById(containerId);
        if (!this.container) {
            throw new Error(`Container with id '${containerId}' not found`);
        }

        if (typeof LightweightCharts === 'undefined') {
            console.error('Lightweight Charts library not loaded!');
            return;
        }

        this.options = {
            width: this.container.clientWidth,
            height: options.height || 250,
            layout: {
                background: { color: '#0F172A' },
                textColor: '#F8FAFC',
            },
            grid: {
                vertLines: { color: '#1E293B' },
                horzLines: { color: '#1E293B' },
            },
            timeScale: {
                borderColor: '#475569',
            },
            rightPriceScale: {
                borderColor: '#475569',
            },
            ...options
        };

        this.chart = LightweightCharts.createChart(this.container, this.options);
        this.areaSeries = this.chart.addAreaSeries({
            topColor: 'rgba(0, 230, 118, 0.4)',
            bottomColor: 'rgba(0, 230, 118, 0.0)',
            lineColor: '#00e676',
            lineWidth: 2,
        });

        this.setupResizeHandler();
    }

    /**
     * Установить данные equity curve.
     * @param {Array} trades - Массив сделок с полями: closed_at, pnl
     */
    setTradesData(trades) {
        let cumulativePnL = 0;
        const equityData = [];

        // Сортировать по времени
        const sortedTrades = [...trades].sort((a, b) =>
            new Date(a.closed_at) - new Date(b.closed_at)
        );

        sortedTrades.forEach(trade => {
            if (trade.status === 'closed' && trade.pnl != null) {
                cumulativePnL += trade.pnl;
                equityData.push({
                    time: Math.floor(new Date(trade.closed_at).getTime() / 1000),
                    value: cumulativePnL
                });
            }
        });

        // Изменить цвет если убыток
        if (cumulativePnL < 0) {
            this.areaSeries.applyOptions({
                topColor: 'rgba(255, 82, 82, 0.4)',
                bottomColor: 'rgba(255, 82, 82, 0.0)',
                lineColor: '#ff5252',
            });
        }

        this.areaSeries.setData(equityData);
    }

    setupResizeHandler() {
        const resizeObserver = new ResizeObserver(entries => {
            if (entries.length === 0 || entries[0].target !== this.container) return;
            const newRect = entries[0].contentRect;
            this.chart.applyOptions({ width: newRect.width });
        });

        resizeObserver.observe(this.container);
    }

    destroy() {
        this.chart.remove();
    }
}

// Export для использования
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { TradingChart, EquityCurveChart };
}
