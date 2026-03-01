/**
 * WebSocket Client - обёртка для socket.io
 *
 * Упрощает работу с WebSocket подключением:
 * - Автоматическое переподключение
 * - Подписка на обновления стратегий
 * - Event handlers с типизацией
 * - Connection status monitoring
 */

class WebSocketClient {
    /**
     * @param {string} url - URL сервера (по умолчанию текущий хост)
     */
    constructor(url = null) {
        this.url = url || window.location.origin;
        this.socket = null;
        this.handlers = {};
        this.subscribedStrategies = new Set();
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;

        this.init();
    }

    /**
     * Инициализация WebSocket соединения.
     */
    init() {
        console.log('[WS] Connecting to:', this.url);

        this.socket = io(this.url, {
            transports: ['websocket', 'polling'],
            reconnection: true,
            reconnectionDelay: 1000,
            reconnectionDelayMax: 5000,
            reconnectionAttempts: this.maxReconnectAttempts
        });

        // Базовые обработчики
        this.socket.on('connect', () => this._onConnect());
        this.socket.on('disconnect', (reason) => this._onDisconnect(reason));
        this.socket.on('error', (error) => this._onError(error));
        this.socket.on('reconnect_attempt', (attempt) => this._onReconnectAttempt(attempt));
        this.socket.on('reconnect', () => this._onReconnect());

        // Пользовательские события
        this.socket.on('connection_response', (data) => this.trigger('connection', data));
        this.socket.on('subscribed', (data) => this.trigger('subscribed', data));
        this.socket.on('trade_update', (data) => this.trigger('trade', data));
        this.socket.on('signal', (data) => this.trigger('signal', data));
        this.socket.on('price_update', (data) => this.trigger('price', data));
        this.socket.on('pong', (data) => this.trigger('pong', data));
    }

    /**
     * Подписаться на обновления стратегии.
     * @param {string|number} strategyId - ID стратегии
     */
    subscribe(strategyId) {
        if (this.subscribedStrategies.has(strategyId)) {
            console.log(`[WS] Already subscribed to strategy ${strategyId}`);
            return;
        }

        this.socket.emit('subscribe', { strategy_id: strategyId });
        this.subscribedStrategies.add(strategyId);
        console.log(`[WS] Subscribed to strategy ${strategyId}`);
    }

    /**
     * Отписаться от обновлений стратегии.
     * @param {string|number} strategyId - ID стратегии
     */
    unsubscribe(strategyId) {
        if (!this.subscribedStrategies.has(strategyId)) {
            return;
        }

        this.socket.emit('unsubscribe', { strategy_id: strategyId });
        this.subscribedStrategies.delete(strategyId);
        console.log(`[WS] Unsubscribed from strategy ${strategyId}`);
    }

    /**
     * Отписаться от всех стратегий.
     */
    unsubscribeAll() {
        this.subscribedStrategies.forEach(id => {
            this.socket.emit('unsubscribe', { strategy_id: id });
        });
        this.subscribedStrategies.clear();
        console.log('[WS] Unsubscribed from all strategies');
    }

    /**
     * Отправить ping для проверки соединения.
     */
    ping() {
        this.socket.emit('ping');
    }

    /**
     * Добавить обработчик события.
     * @param {string} event - имя события (connection, trade, signal, price, pong)
     * @param {Function} handler - функция-обработчик
     */
    on(event, handler) {
        if (!this.handlers[event]) {
            this.handlers[event] = [];
        }
        this.handlers[event].push(handler);
    }

    /**
     * Удалить обработчик события.
     * @param {string} event - имя события
     * @param {Function} handler - функция-обработчик
     */
    off(event, handler) {
        if (!this.handlers[event]) return;

        this.handlers[event] = this.handlers[event].filter(h => h !== handler);
    }

    /**
     * Вызвать все обработчики события.
     * @param {string} event - имя события
     * @param {any} data - данные события
     */
    trigger(event, data) {
        if (!this.handlers[event]) return;

        this.handlers[event].forEach(handler => {
            try {
                handler(data);
            } catch (error) {
                console.error(`[WS] Error in ${event} handler:`, error);
            }
        });
    }

    /**
     * Проверить статус соединения.
     * @returns {boolean} true если подключено
     */
    isConnected() {
        return this.socket && this.socket.connected;
    }

    /**
     * Закрыть соединение.
     */
    disconnect() {
        console.log('[WS] Disconnecting...');
        this.unsubscribeAll();
        if (this.socket) {
            this.socket.disconnect();
        }
    }

    // ============================================================
    // Internal handlers
    // ============================================================

    _onConnect() {
        console.log('[WS] Connected');
        this.reconnectAttempts = 0;
        this.trigger('status_change', { connected: true });

        // Повторно подписаться на стратегии
        if (this.subscribedStrategies.size > 0) {
            console.log('[WS] Re-subscribing to strategies...');
            this.subscribedStrategies.forEach(id => {
                this.socket.emit('subscribe', { strategy_id: id });
            });
        }
    }

    _onDisconnect(reason) {
        console.log('[WS] Disconnected:', reason);
        this.trigger('status_change', { connected: false, reason });
    }

    _onError(error) {
        console.error('[WS] Error:', error);
        this.trigger('error', error);
    }

    _onReconnectAttempt(attempt) {
        console.log(`[WS] Reconnect attempt ${attempt}/${this.maxReconnectAttempts}`);
        this.reconnectAttempts = attempt;
    }

    _onReconnect() {
        console.log('[WS] Reconnected');
        this.trigger('reconnected', {});
    }
}

// Export для использования в других скриптах
if (typeof module !== 'undefined' && module.exports) {
    module.exports = WebSocketClient;
}
