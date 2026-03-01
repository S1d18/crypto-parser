"""
Strategy Manager - управление всеми торговыми стратегиями.

Функции:
- Запуск/остановка стратегий
- Получение свечей с Bybit
- Проверка сигналов и Stop Loss
- Сохранение сделок в БД
"""
import asyncio
import logging
import time
from typing import Dict, List, Optional
from datetime import datetime
import json

import ccxt

from core.database import Database
from strategies.supertrend_strategy import SupertrendStrategy
from strategies.rsi_strategy import RSIStrategy
from strategies.macd_strategy import MACDStrategy


logger = logging.getLogger("strategy_manager")


class StrategyManager:
    """Менеджер для управления торговыми стратегиями."""

    def __init__(self, exchange: ccxt.Exchange, db: Database):
        """
        Args:
            exchange: ccxt exchange instance (Bybit demo)
            db: Database instance
        """
        self.exchange = exchange
        self.db = db
        self.strategies: Dict[int, any] = {}  # strategy_id → strategy instance
        self.running = False

    def load_strategy_from_db(self, strategy_data: Dict) -> Optional[any]:
        """
        Создать экземпляр стратегии из данных БД.

        Args:
            strategy_data: Словарь с данными стратегии из БД

        Returns:
            Экземпляр стратегии или None
        """
        strategy_id = strategy_data['id']
        strategy_type = strategy_data['type']
        name = strategy_data['name']
        timeframe = strategy_data['timeframe']
        direction = strategy_data['direction']
        virtual_balance = strategy_data.get('virtual_balance', 1000.0)
        position_size_pct = strategy_data.get('position_size_pct', 10.0)
        sl_percent = strategy_data.get('sl_percent', 10.0)

        # Парсить параметры из JSON
        try:
            params = json.loads(strategy_data['params']) if strategy_data['params'] else {}
        except (json.JSONDecodeError, TypeError):
            params = {}

        # Получить символ из БД (по умолчанию BTC)
        symbol = strategy_data.get('symbol', 'BTC/USDT:USDT')

        # Создать экземпляр стратегии
        if strategy_type == 'supertrend':
            return SupertrendStrategy(
                strategy_id=strategy_id,
                name=name,
                symbol=symbol,
                timeframe=timeframe,
                direction=direction,
                virtual_balance=virtual_balance,
                position_size_pct=position_size_pct,
                sl_percent=sl_percent,
                params=params
            )
        elif strategy_type == 'rsi':
            return RSIStrategy(
                strategy_id=strategy_id,
                name=name,
                symbol=symbol,
                timeframe=timeframe,
                direction=direction,
                virtual_balance=virtual_balance,
                position_size_pct=position_size_pct,
                sl_percent=sl_percent,
                params=params
            )
        elif strategy_type == 'macd':
            return MACDStrategy(
                strategy_id=strategy_id,
                name=name,
                symbol=symbol,
                timeframe=timeframe,
                direction=direction,
                virtual_balance=virtual_balance,
                position_size_pct=position_size_pct,
                sl_percent=sl_percent,
                params=params
            )
        else:
            logger.warning(f"Unknown strategy type: {strategy_type}")
            return None

    def restore_open_position(self, strategy: any):
        """Восстановить открытую позицию из БД для стратегии."""
        try:
            cursor = self.db.conn.execute("""
                SELECT side, qty, entry_price, sl_price, opened_at, fees
                FROM trades
                WHERE strategy_id = ? AND status = 'open'
                ORDER BY opened_at DESC
                LIMIT 1
            """, (strategy.strategy_id,))

            row = cursor.fetchone()
            if row:
                # Восстановить позицию в памяти стратегии
                strategy.position = {
                    'side': row[0],
                    'qty': row[1],
                    'price': row[2],
                    'sl_price': row[3],
                    'opened_at': datetime.fromisoformat(row[4]),
                    'entry_fee': row[5] if row[5] else 0
                }
                logger.info(f"[{strategy.name}] Восстановлена позиция {row[0].upper()} @ {row[2]:,.2f}")
        except Exception as e:
            logger.error(f"Error restoring position for {strategy.name}: {e}")

    async def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 100) -> List[List]:
        """
        Получить свечи с биржи (с кэшированием для избежания дублирующих запросов).

        Args:
            symbol: Торговая пара
            timeframe: Таймфрейм
            limit: Количество свечей

        Returns:
            Список свечей [[timestamp, open, high, low, close, volume], ...]
        """
        from core.ohlcv_cache import get_ohlcv_cache

        cache = get_ohlcv_cache()

        # Проверить кэш
        cached_data = cache.get(symbol, timeframe)
        if cached_data is not None:
            logger.debug(f"OHLCV cache HIT: {symbol} {timeframe}")
            return cached_data

        # Кэш пустой - запросить с биржи
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)

            # Сохранить в кэш
            cache.set(symbol, timeframe, ohlcv)
            logger.debug(f"OHLCV cache MISS: {symbol} {timeframe} (fetched and cached)")

            return ohlcv
        except Exception as e:
            logger.error(f"Error fetching OHLCV {symbol} {timeframe}: {e}")
            return []

    async def process_strategy(self, strategy: any):
        """
        Обработать одну стратегию (проверить сигналы, SL).

        Args:
            strategy: Экземпляр стратегии
        """
        try:
            # Получить свечи
            ohlcv = await self.fetch_ohlcv(strategy.symbol, strategy.timeframe)

            if not ohlcv or len(ohlcv) < 50:
                logger.warning(f"[{strategy.name}] Недостаточно свечей: {len(ohlcv)}")
                return

            current_price = ohlcv[-1][4]  # close price

            # Проверить Stop Loss
            if strategy.check_stop_loss(current_price):
                result = strategy.close_position(current_price, reason='sl_hit')
                await self._update_closed_trade(result)
                await self._update_virtual_balance(strategy)
                return

            # Рассчитать сигнал
            signal = strategy.calculate_signal(ohlcv)

            if signal is None:
                return

            # Обработать сигнал
            if signal == 'buy':
                # Если есть открытая позиция - закрыть её
                if strategy.position is not None:
                    result = strategy.close_position(current_price, reason='signal')
                    await self._update_closed_trade(result)
                    await self._update_virtual_balance(strategy)
                    logger.info(f"[{strategy.name}] Закрыта старая позиция перед открытием Long")

                position = strategy.open_position('buy', current_price)
                logger.info(f"[{strategy.name}] Открыта Long позиция @ {current_price:,.2f}")
                await self._save_open_position(position)

            elif signal == 'sell':
                # Если есть открытая позиция - закрыть её
                if strategy.position is not None:
                    result = strategy.close_position(current_price, reason='signal')
                    await self._update_closed_trade(result)
                    await self._update_virtual_balance(strategy)
                    logger.info(f"[{strategy.name}] Закрыта старая позиция перед открытием Short")

                position = strategy.open_position('sell', current_price)
                logger.info(f"[{strategy.name}] Открыта Short позиция @ {current_price:,.2f}")
                await self._save_open_position(position)

            elif signal == 'close':
                result = strategy.close_position(current_price, reason='signal')
                await self._update_closed_trade(result)
                await self._update_virtual_balance(strategy)

        except Exception as e:
            logger.error(f"Error processing strategy {strategy.name}: {e}", exc_info=True)

    async def _save_open_position(self, position: Dict):
        """Сохранить открытую позицию в БД (TradingView style)."""
        if not position:
            return

        try:
            self.db.conn.execute("""
                INSERT INTO trades (
                    strategy_id, symbol, side, direction, qty, leverage,
                    entry_price, sl_price, opened_at, fees, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                position['strategy_id'],
                position['symbol'],
                position['side'],
                position['direction'],
                position['qty'],
                1,  # leverage
                position['entry_price'],
                position['sl_price'],
                position['opened_at'],
                position['fees'],
                'open'
            ))
            self.db.conn.commit()

            logger.info(f"✓ Open position saved to DB: {position['strategy_id']} | Entry: ${position['entry_price']:,.2f}")

        except Exception as e:
            logger.error(f"Error saving open position: {e}", exc_info=True)

    async def _update_closed_trade(self, trade_data: Dict):
        """Обновить закрытую сделку в БД (было открытой, стала закрытой)."""
        if not trade_data:
            return

        try:
            # Найти открытую позицию этой стратегии
            cursor = self.db.conn.execute("""
                SELECT id FROM trades
                WHERE strategy_id = ? AND status = 'open'
                ORDER BY opened_at DESC
                LIMIT 1
            """, (trade_data['strategy_id'],))

            row = cursor.fetchone()
            if not row:
                logger.warning(f"No open position found for strategy {trade_data['strategy_id']}")
                return

            trade_id = row[0]

            # Обновить запись - закрыть позицию
            self.db.conn.execute("""
                UPDATE trades
                SET close_price = ?,
                    closed_at = ?,
                    close_reason = ?,
                    pnl = ?,
                    pnl_percent = ?,
                    fees = fees + ?,
                    status = 'closed'
                WHERE id = ?
            """, (
                trade_data['close_price'],
                trade_data['closed_at'],
                trade_data['close_reason'],
                trade_data['pnl'],
                trade_data['pnl_percent'],
                trade_data.get('exit_fee', 0),
                trade_id
            ))
            self.db.conn.commit()

            logger.info(f"✓ Trade closed in DB: #{trade_id} | PnL: ${trade_data['pnl']:+.2f}")

        except Exception as e:
            logger.error(f"Error updating closed trade: {e}", exc_info=True)

    async def _save_trade(self, trade_data: Dict):
        """Сохранить сделку в БД."""
        if not trade_data:
            return

        try:
            self.db.conn.execute("""
                INSERT INTO trades (
                    strategy_id, symbol, side, direction, qty, leverage,
                    entry_price, close_price, sl_price,
                    opened_at, closed_at, close_reason,
                    pnl, pnl_percent, fees, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trade_data['strategy_id'],
                trade_data['symbol'],
                trade_data['side'],
                trade_data['direction'],
                trade_data['qty'],
                1,  # leverage (для paper trading всегда 1)
                trade_data['entry_price'],
                trade_data['close_price'],
                trade_data['sl_price'],
                trade_data['opened_at'],
                trade_data['closed_at'],
                trade_data['close_reason'],
                trade_data['pnl'],
                trade_data['pnl_percent'],
                trade_data['fees'],
                'closed'
            ))
            self.db.conn.commit()

            logger.info(f"Trade saved to DB: {trade_data['strategy_id']} | PnL: ${trade_data['pnl']:+.2f}")

        except Exception as e:
            logger.error(f"Error saving trade: {e}", exc_info=True)

    async def _update_virtual_balance(self, strategy: any):
        """Обновить виртуальный баланс стратегии в БД."""
        try:
            self.db.conn.execute("""
                UPDATE strategies
                SET virtual_balance = ?
                WHERE id = ?
            """, (strategy.virtual_balance, strategy.strategy_id))
            self.db.conn.commit()

        except Exception as e:
            logger.error(f"Error updating virtual balance: {e}", exc_info=True)

    async def run_loop(self):
        """Главный цикл обработки стратегий."""
        logger.info("StrategyManager loop started")

        while self.running:
            try:
                # Получить активные стратегии
                active_strategies_data = self.db.get_strategies_by_status('running')

                # Загрузить стратегии если ещё не загружены
                for strategy_data in active_strategies_data:
                    strategy_id = strategy_data['id']

                    if strategy_id not in self.strategies:
                        strategy = self.load_strategy_from_db(strategy_data)
                        if strategy:
                            self.strategies[strategy_id] = strategy
                            logger.info(f"Loaded strategy: {strategy.name}")
                            # Восстановить открытую позицию из БД
                            self.restore_open_position(strategy)

                # Обработать каждую стратегию
                if self.strategies:
                    for strategy_id, strategy in list(self.strategies.items()):
                        await self.process_strategy(strategy)

                # Убрать остановленные стратегии
                all_running_ids = [s['id'] for s in active_strategies_data]
                for strategy_id in list(self.strategies.keys()):
                    if strategy_id not in all_running_ids:
                        del self.strategies[strategy_id]
                        logger.info(f"Removed stopped strategy: {strategy_id}")

                # Пауза между циклами (30 секунд)
                await asyncio.sleep(30)

            except Exception as e:
                logger.error(f"Error in StrategyManager loop: {e}", exc_info=True)
                await asyncio.sleep(5)

        logger.info("StrategyManager loop stopped")

    def start(self):
        """Запустить менеджер стратегий."""
        self.running = True
        logger.info("StrategyManager started")

    def stop(self):
        """Остановить менеджер стратегий."""
        self.running = False
        self.strategies.clear()
        logger.info("StrategyManager stopped")
