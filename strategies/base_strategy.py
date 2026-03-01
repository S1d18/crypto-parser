"""
Базовый класс для всех торговых стратегий.

Поддерживает:
- Paper trading с виртуальным балансом
- Автоматический Stop Loss
- Расчёт PnL с комиссиями
- Восстановление позиций из БД
"""
import logging
from datetime import datetime
from typing import Optional, Dict, List
from abc import ABC, abstractmethod

import ccxt


class Strategy(ABC):
    """Базовый класс для торговой стратегии."""

    def __init__(self, strategy_id: int, name: str, symbol: str, timeframe: str,
                 direction: str, virtual_balance: float, position_size_pct: float,
                 sl_percent: float, params: dict):
        """
        Args:
            strategy_id: ID стратегии в БД
            name: Название стратегии
            symbol: Торговая пара (BTCUSDT, ETHUSDT, и т.д.)
            timeframe: Таймфрейм (1m, 5m, 15m, 1h, 4h, 1d)
            direction: Направление торговли (long, short, both)
            virtual_balance: Виртуальный баланс (USDT)
            position_size_pct: Размер позиции в % от баланса
            sl_percent: Stop Loss в % от цены входа
            params: Параметры индикатора (period, multiplier, и т.д.)
        """
        self.strategy_id = strategy_id
        self.name = name
        self.symbol = symbol
        self.timeframe = timeframe
        self.direction = direction
        self.virtual_balance = virtual_balance
        self.position_size_pct = position_size_pct
        self.sl_percent = sl_percent
        self.params = params

        # Текущая позиция (None если нет позиции)
        self.position: Optional[Dict] = None

        # Logger
        self.logger = logging.getLogger(f"strategy.{name}")

        # Комиссия биржи (Bybit taker)
        self.TAKER_FEE = 0.00055  # 0.055%

    @abstractmethod
    def calculate_signal(self, ohlcv: List[List]) -> Optional[str]:
        """
        Рассчитать торговый сигнал на основе свечей.

        Args:
            ohlcv: Список свечей [[timestamp, open, high, low, close, volume], ...]

        Returns:
            'buy' - открыть Long
            'sell' - открыть Short
            'close' - закрыть позицию
            None - нет сигнала
        """
        pass

    def can_open_long(self) -> bool:
        """Проверить можно ли открыть Long позицию."""
        # Разрешить если нет позиции ИЛИ есть Short позиция (переворот)
        if self.position is not None and self.position['side'] == 'buy':
            return False  # Уже в Long
        return self.direction in ['long', 'both']

    def can_open_short(self) -> bool:
        """Проверить можно ли открыть Short позицию."""
        # Разрешить если нет позиции ИЛИ есть Long позиция (переворот)
        if self.position is not None and self.position['side'] == 'sell':
            return False  # Уже в Short
        return self.direction in ['short', 'both']

    def open_position(self, side: str, price: float) -> Dict:
        """
        Открыть виртуальную позицию.

        Args:
            side: 'buy' (Long) или 'sell' (Short)
            price: Цена входа

        Returns:
            Dict с данными позиции
        """
        # Рассчитать размер позиции
        position_value = self.virtual_balance * (self.position_size_pct / 100)
        qty = position_value / price

        # Рассчитать Stop Loss
        if side == 'buy':
            sl_price = price * (1 - self.sl_percent / 100)
        else:  # sell
            sl_price = price * (1 + self.sl_percent / 100)

        # Вычесть комиссию за открытие
        entry_fee = position_value * self.TAKER_FEE
        self.virtual_balance -= entry_fee

        self.position = {
            'side': side,
            'price': price,
            'qty': qty,
            'sl_price': sl_price,
            'opened_at': datetime.now(),
            'entry_fee': entry_fee
        }

        self.logger.info(f"Открыта позиция {side.upper()} @ {price:,.2f} | "
                        f"Qty: {qty:.6f} | SL: {sl_price:,.2f} | Fee: ${entry_fee:.2f}")

        # Возвратить полные данные для сохранения в БД
        return {
            'strategy_id': self.strategy_id,
            'symbol': self.symbol,
            'side': side,
            'direction': 'long' if side == 'buy' else 'short',
            'qty': qty,
            'entry_price': price,
            'sl_price': sl_price,
            'opened_at': self.position['opened_at'].isoformat(),
            'fees': entry_fee
        }

    def close_position(self, price: float, reason: str = "signal") -> Dict:
        """
        Закрыть виртуальную позицию.

        Args:
            price: Цена закрытия
            reason: Причина закрытия ('signal', 'sl_hit')

        Returns:
            Dict с результатами сделки
        """
        if self.position is None:
            self.logger.warning("Попытка закрыть несуществующую позицию")
            return {}

        side = self.position['side']
        entry_price = self.position['price']
        qty = self.position['qty']
        entry_fee = self.position['entry_fee']

        # Рассчитать PnL
        if side == 'buy':  # Long
            pnl_gross = (price - entry_price) * qty
        else:  # Short
            pnl_gross = (entry_price - price) * qty

        # Вычесть комиссию за закрытие
        exit_value = price * qty
        exit_fee = exit_value * self.TAKER_FEE
        pnl_net = pnl_gross - entry_fee - exit_fee

        # Обновить виртуальный баланс (ТОЛЬКО PnL, не exit_value)
        self.virtual_balance += pnl_net

        result = {
            'strategy_id': self.strategy_id,
            'symbol': self.symbol,
            'side': side,
            'direction': 'long' if side == 'buy' else 'short',
            'qty': qty,
            'entry_price': entry_price,
            'close_price': price,
            'sl_price': self.position['sl_price'],
            'opened_at': self.position['opened_at'].isoformat(),
            'closed_at': datetime.now().isoformat(),
            'close_reason': reason,
            'pnl': pnl_net,
            'pnl_percent': (pnl_net / (entry_price * qty)) * 100,
            'fees': entry_fee + exit_fee,
            'exit_fee': exit_fee,
            'new_balance': self.virtual_balance
        }

        self.logger.info(f"Закрыта позиция {side.upper()} @ {price:,.2f} | "
                        f"PnL: ${pnl_net:+.2f} ({result['pnl_percent']:+.2f}%) | "
                        f"Balance: ${self.virtual_balance:,.2f}")

        self.position = None
        return result

    def check_stop_loss(self, current_price: float) -> bool:
        """
        Проверить сработал ли Stop Loss.

        Args:
            current_price: Текущая цена

        Returns:
            True если SL сработал
        """
        if self.position is None:
            return False

        side = self.position['side']
        sl_price = self.position['sl_price']

        if side == 'buy':  # Long
            if current_price <= sl_price:
                self.logger.warning(f"Stop Loss сработал! Price: {current_price:,.2f} <= SL: {sl_price:,.2f}")
                return True
        else:  # Short
            if current_price >= sl_price:
                self.logger.warning(f"Stop Loss сработал! Price: {current_price:,.2f} >= SL: {sl_price:,.2f}")
                return True

        return False

    def get_status(self) -> Dict:
        """Получить текущий статус стратегии."""
        return {
            'strategy_id': self.strategy_id,
            'name': self.name,
            'symbol': self.symbol,
            'timeframe': self.timeframe,
            'direction': self.direction,
            'virtual_balance': self.virtual_balance,
            'position': self.position,
            'params': self.params
        }
