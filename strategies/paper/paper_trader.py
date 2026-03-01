import logging
import time

from strategies.paper.strategies import PaperStrategyConfig
from strategies.paper.paper_storage import PaperTradeStorage
from core.supertrend import calculate_supertrend

logger = logging.getLogger(__name__)

SYMBOL = "BTC/USDT:USDT"


class PaperTrader:
    def __init__(self, strategies: list[PaperStrategyConfig], storage: PaperTradeStorage):
        self.strategies = strategies
        self.storage = storage
        self.positions: dict[str, dict] = {}       # strategy_id -> позиция
        self.last_directions: dict[str, int] = {}   # strategy_id -> направление ST
        self.last_check: dict[str, float] = {}      # timeframe -> timestamp

        # Группировка стратегий по таймфрейму
        self.tf_strategies: dict[str, list[PaperStrategyConfig]] = {}
        for s in strategies:
            self.tf_strategies.setdefault(s.timeframe, []).append(s)

        # Восстановление открытых позиций из БД
        self._recover_positions()

    def _recover_positions(self):
        open_trades = self.storage.get_open_trades()
        for trade in open_trades:
            sid = trade["strategy_id"]
            self.positions[sid] = {
                "side": trade["side"],
                "qty": trade["qty"],
                "entry_price": trade["entry_price"],
                "sl_price": trade["sl_price"],
                "direction": trade["direction"],
            }
            logger.info(f"[Paper] Восстановлена позиция {sid}: {trade['side']} @ {trade['entry_price']}")

    def get_unique_timeframes(self) -> set[str]:
        return set(s.timeframe for s in self.strategies)

    def should_check(self, timeframe: str) -> bool:
        now = time.time()
        tf_seconds = self._timeframe_to_seconds(timeframe)
        last = self.last_check.get(timeframe, 0)

        if last == 0:
            return True

        current_candle = int(now // tf_seconds)
        last_candle = int(last // tf_seconds)

        if current_candle > last_candle:
            candle_start = current_candle * tf_seconds
            if (now - candle_start) >= 5:
                return True
        return False

    def process_timeframe(self, timeframe: str, ohlcv: list[list]):
        """Обрабатывает все paper-стратегии на данном ТФ."""
        strategies = self.tf_strategies.get(timeframe, [])
        if not strategies:
            return

        current_price = ohlcv[-1][4]

        # Сначала проверяем SL по текущей цене
        for strategy in strategies:
            self._check_sl_hit(strategy, ohlcv)

        # Затем проверяем сигналы
        for strategy in strategies:
            self._check_strategy(strategy, ohlcv)

        self.last_check[timeframe] = time.time()

    def _check_strategy(self, strategy: PaperStrategyConfig, ohlcv: list[list]):
        sid = strategy.strategy_id
        try:
            st = calculate_supertrend(ohlcv, strategy.st_period, strategy.st_multiplier)
            current_price = ohlcv[-1][4]

            prev_direction = self.last_directions.get(sid)
            self.last_directions[sid] = st["direction"]

            # Первый запуск — запоминаем направление
            if prev_direction is None:
                logger.info(f"[Paper:{sid}] Первый запуск, направление: {st['direction']}")
                return

            direction_changed = st["direction"] != prev_direction
            if not direction_changed:
                return

            has_position = sid in self.positions

            logger.info(f"[Paper:{sid}] Смена направления: {prev_direction} -> {st['direction']}, price={current_price:.2f}")

            if strategy.direction == "long":
                if st["direction"] == 1 and not has_position:
                    self._open_position(strategy, 1, current_price)
                elif st["direction"] == -1 and has_position:
                    self._close_position(strategy, current_price, "signal")

            elif strategy.direction == "short":
                if st["direction"] == -1 and not has_position:
                    self._open_position(strategy, -1, current_price)
                elif st["direction"] == 1 and has_position:
                    self._close_position(strategy, current_price, "signal")

            elif strategy.direction == "both":
                if has_position:
                    self._close_position(strategy, current_price, "signal")
                    self._open_position(strategy, st["direction"], current_price)
                else:
                    self._open_position(strategy, st["direction"], current_price)

        except Exception as e:
            logger.error(f"[Paper:{sid}] Ошибка check_strategy: {e}", exc_info=True)

    def _check_sl_hit(self, strategy: PaperStrategyConfig, ohlcv: list[list]):
        sid = strategy.strategy_id
        if sid not in self.positions:
            return

        pos = self.positions[sid]
        sl_price = pos.get("sl_price")
        if sl_price is None:
            return

        # Проверяем, пробила ли свеча SL (по low/high последней свечи)
        last_candle = ohlcv[-1]
        low = last_candle[3]
        high = last_candle[2]

        sl_hit = False
        if pos["direction"] == 1 and low <= sl_price:  # Long — SL снизу
            sl_hit = True
        elif pos["direction"] == -1 and high >= sl_price:  # Short — SL сверху
            sl_hit = True

        if sl_hit:
            logger.info(f"[Paper:{sid}] SL hit @ {sl_price}")
            self._close_position(strategy, sl_price, "sl_hit")

    def _open_position(self, strategy: PaperStrategyConfig, direction: int, price: float):
        sid = strategy.strategy_id
        if sid in self.positions:
            return

        side = "buy" if direction == 1 else "sell"
        qty = strategy.virtual_balance / price
        sl_price = self._calc_sl_price(price, direction, strategy.sl_percent)

        self.positions[sid] = {
            "side": side,
            "qty": qty,
            "entry_price": price,
            "sl_price": sl_price,
            "direction": direction,
        }

        self.storage.save_open_trade(
            strategy_id=sid,
            strategy_group=strategy.group,
            timeframe=strategy.timeframe,
            symbol=SYMBOL,
            side=side,
            direction=direction,
            qty=qty,
            entry_price=price,
            sl_price=sl_price,
        )

        logger.info(f"[Paper:{sid}] OPEN {side} qty={qty:.6f} @ {price:.2f}, SL={sl_price:.2f}")

    def _close_position(self, strategy: PaperStrategyConfig, close_price: float, reason: str):
        sid = strategy.strategy_id
        if sid not in self.positions:
            return

        pos = self.positions[sid]

        if pos["direction"] == 1:  # Long
            pnl = (close_price - pos["entry_price"]) * pos["qty"]
        else:  # Short
            pnl = (pos["entry_price"] - close_price) * pos["qty"]

        pnl_pct = (pnl / strategy.virtual_balance) * 100

        self.storage.close_trade(sid, close_price, reason, pnl, pnl_pct)

        logger.info(f"[Paper:{sid}] CLOSE {reason} @ {close_price:.2f}, PnL={pnl:+.2f} ({pnl_pct:+.2f}%)")
        del self.positions[sid]

    def _calc_sl_price(self, entry_price: float, direction: int, sl_percent: float) -> float:
        if direction == 1:
            return round(entry_price * (1 - sl_percent / 100), 2)
        else:
            return round(entry_price * (1 + sl_percent / 100), 2)

    def _timeframe_to_seconds(self, tf: str) -> int:
        mapping = {
            "1m": 60, "3m": 180, "5m": 300, "15m": 900,
            "30m": 1800, "1h": 3600, "2h": 7200, "4h": 14400,
            "6h": 21600, "12h": 43200, "1d": 86400,
        }
        return mapping.get(tf, 3600)
