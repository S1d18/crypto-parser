"""
WebSocket обработчики для real-time updates.

События:
- connect - клиент подключился
- disconnect - клиент отключился
- subscribe - подписка на обновления стратегии
- unsubscribe - отписка от обновлений

Server → Client события:
- connection_response - подтверждение подключения
- subscribed - подтверждение подписки
- trade_update - обновление сделки
- signal - новый сигнал
- price_update - обновление цены
"""
import logging
from flask import request
from flask_socketio import emit, join_room, leave_room
from datetime import datetime

logger = logging.getLogger(__name__)


def init_websocket_handlers(socketio, app):
    """Инициализация WebSocket обработчиков."""

    @socketio.on('connect')
    def handle_connect():
        """Клиент подключился."""
        client_id = request.sid
        logger.info(f"Client connected: {client_id}")
        emit('connection_response', {
            'status': 'connected',
            'client_id': client_id,
            'timestamp': datetime.now().isoformat()
        })

    @socketio.on('disconnect')
    def handle_disconnect():
        """Клиент отключился."""
        client_id = request.sid
        logger.info(f"Client disconnected: {client_id}")

    @socketio.on('subscribe')
    def handle_subscribe(data):
        """
        Подписка на обновления стратегии.

        Args:
            data: {'strategy_id': int}
        """
        strategy_id = data.get('strategy_id')
        if not strategy_id:
            emit('error', {'message': 'strategy_id required'})
            return

        room_name = f'strategy_{strategy_id}'
        join_room(room_name)

        logger.info(f"Client {request.sid} subscribed to strategy {strategy_id}")
        emit('subscribed', {
            'strategy_id': strategy_id,
            'room': room_name
        })

    @socketio.on('unsubscribe')
    def handle_unsubscribe(data):
        """
        Отписка от обновлений стратегии.

        Args:
            data: {'strategy_id': int}
        """
        strategy_id = data.get('strategy_id')
        if not strategy_id:
            return

        room_name = f'strategy_{strategy_id}'
        leave_room(room_name)

        logger.info(f"Client {request.sid} unsubscribed from strategy {strategy_id}")

    @socketio.on('ping')
    def handle_ping():
        """Ping для проверки соединения."""
        emit('pong', {'timestamp': datetime.now().isoformat()})

    # ============================================================
    # Broadcast функции (вызываются из других модулей)
    # ============================================================

    def broadcast_trade(strategy_id, trade_data):
        """
        Отправить обновление о сделке всем подписчикам.

        Args:
            strategy_id: ID стратегии
            trade_data: данные сделки (dict)
        """
        room_name = f'strategy_{strategy_id}'
        socketio.emit('trade_update', trade_data, room=room_name)
        logger.debug(f"Broadcasted trade update to {room_name}")

    def broadcast_signal(strategy_id, signal_data):
        """
        Отправить сигнал всем подписчикам.

        Args:
            strategy_id: ID стратегии
            signal_data: данные сигнала (dict)
        """
        room_name = f'strategy_{strategy_id}'
        socketio.emit('signal', signal_data, room=room_name)
        logger.debug(f"Broadcasted signal to {room_name}")

    def broadcast_price(symbol, price):
        """
        Отправить обновление цены всем клиентам.

        Args:
            symbol: символ (e.g., 'BTCUSDT')
            price: текущая цена
        """
        socketio.emit('price_update', {
            'symbol': symbol,
            'price': price,
            'timestamp': datetime.now().isoformat()
        }, broadcast=True)

    # Сохранить broadcast функции в app.config для доступа из других модулей
    app.config['broadcast_trade'] = broadcast_trade
    app.config['broadcast_signal'] = broadcast_signal
    app.config['broadcast_price'] = broadcast_price

    logger.info("✓ WebSocket handlers registered")
