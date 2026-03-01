import asyncio
import logging
import signal
import sys
import time
from datetime import datetime, timezone

import ccxt

from core.config import Config, StrategyConfig
from core.supertrend import calculate_supertrend
from core.notifier import TelegramNotifier
from core.storage import TradeStorage
from strategies.paper.strategies import PAPER_STRATEGIES
from strategies.paper.paper_trader import PaperTrader
from strategies.paper.paper_storage import PaperTradeStorage

# Константы
BYBIT_TAKER_FEE = 0.00055  # 0.055% taker fee

# Логирование
def setup_logging(log_file: str):
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    handlers = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file, encoding="utf-8"),
    ]
    logging.basicConfig(level=logging.INFO, format=fmt, handlers=handlers)


logger = logging.getLogger("bot")


class SupertrendBot:
    def __init__(self, config: Config):
        self.config = config
        self.notifier = TelegramNotifier(config.telegram_token, config.telegram_chat_id)
        self.exchange = self._init_exchange()
        self.storage = TradeStorage()
        self.positions: dict[str, dict] = {}  # timeframe -> {"side", "qty", "entry_price", "sl_order_id"}
        self.last_check: dict[str, float] = {}  # timeframe -> timestamp последней проверки
        self.last_directions: dict[str, int] = {}  # timeframe -> последнее направление ST
        self.running = True

        # Paper trading
        self.paper_storage = PaperTradeStorage()
        self.paper_trader = PaperTrader(PAPER_STRATEGIES, self.paper_storage)

    def _init_exchange(self) -> ccxt.bybit:
        exchange = ccxt.bybit({
            "apiKey": self.config.bybit_api_key,
            "secret": self.config.bybit_api_secret,
            "options": {
                "defaultType": "swap",
                "adjustForTimeDifference": True,
            },
            "enableRateLimit": True,
        })

        if self.config.bybit_demo:
            exchange.enable_demo_trading(True)

        logger.info(f"Exchange: Bybit {'DEMO (api-demo.bybit.com)' if self.config.bybit_demo else 'LIVE'}")
        return exchange

    def fetch_candles(self, timeframe: str, limit: int = None) -> list[list]:
        limit = limit or self.config.candles_limit
        logger.info(f"Получаю {limit} свечей {timeframe} для {self.config.symbol}")
        ohlcv = self.exchange.fetch_ohlcv(
            self.config.symbol,
            timeframe=timeframe,
            limit=limit,
        )
        if not ohlcv:
            raise ValueError(f"Биржа вернула 0 свечей для {timeframe}")
        logger.info(f"Получено {len(ohlcv)} свечей, последняя: {datetime.fromtimestamp(ohlcv[-1][0]/1000, tz=timezone.utc)}")
        return ohlcv

    def check_signal(self, strategy: StrategyConfig) -> dict | None:
        """
        Проверяет сигнал Supertrend для стратегии.
        Возвращает {"action": "open"/"close"/"none", "direction": 1/-1, "price": float}
        """
        try:
            ohlcv = self.fetch_candles(strategy.timeframe)
            st = calculate_supertrend(ohlcv, strategy.st_period, strategy.st_multiplier)
            current_price = ohlcv[-1][4]

            logger.info(
                f"[{strategy.timeframe}] ST direction={st['direction']}, "
                f"changed={st['changed']}, price={current_price:.2f}, "
                f"ST={st['supertrend']:.2f}"
            )

            prev_direction = self.last_directions.get(strategy.timeframe)
            self.last_directions[strategy.timeframe] = st["direction"]

            # Первый запуск — запоминаем направление, не торгуем
            if prev_direction is None:
                logger.info(f"[{strategy.timeframe}] Первый запуск, запоминаю направление: {st['direction']}")
                self.notifier.notify_signal(strategy.timeframe, st["direction"], current_price, changed=False)
                return {"action": "none", "direction": st["direction"], "price": current_price}

            has_position = strategy.timeframe in self.positions
            direction_changed = st["direction"] != prev_direction

            if not direction_changed:
                return {"action": "none", "direction": st["direction"], "price": current_price}

            # Направление изменилось
            self.notifier.notify_signal(strategy.timeframe, st["direction"], current_price, changed=True)

            if strategy.direction == "long":
                if st["direction"] == 1 and not has_position:
                    return {"action": "open", "direction": 1, "price": current_price}
                elif st["direction"] == -1 and has_position:
                    return {"action": "close", "direction": -1, "price": current_price}

            elif strategy.direction == "short":
                if st["direction"] == -1 and not has_position:
                    return {"action": "open", "direction": -1, "price": current_price}
                elif st["direction"] == 1 and has_position:
                    return {"action": "close", "direction": 1, "price": current_price}

            elif strategy.direction == "both":
                if has_position:
                    return {"action": "close_and_reverse", "direction": st["direction"], "price": current_price}
                else:
                    return {"action": "open", "direction": st["direction"], "price": current_price}

            return {"action": "none", "direction": st["direction"], "price": current_price}

        except Exception as e:
            logger.error(f"[{strategy.timeframe}] Ошибка check_signal: {e}", exc_info=True)
            self.notifier.notify_error(f"[{strategy.timeframe}] check_signal: {e}")
            return None

    def calculate_qty(self, strategy: StrategyConfig, price: float) -> float:
        try:
            balance = self.exchange.fetch_balance()
            usdt_free = float(balance.get("USDT", {}).get("free", 0))
            position_usdt = usdt_free * (strategy.position_size_pct / 100)
            position_usdt = min(position_usdt, self.config.max_position_usdt)
            qty = position_usdt / price

            # Округление по правилам биржи
            market = self.exchange.market(self.config.symbol)
            qty = self.exchange.amount_to_precision(self.config.symbol, qty)
            qty = float(qty)

            logger.info(f"Balance: {usdt_free:.2f} USDT, Position: {position_usdt:.2f} USDT, Qty: {qty}")
            return qty
        except Exception as e:
            logger.error(f"Ошибка calculate_qty: {e}", exc_info=True)
            return 0

    def open_position(self, strategy: StrategyConfig, direction: int, price: float) -> bool:
        side = "buy" if direction == 1 else "sell"
        tf = strategy.timeframe

        if tf in self.positions:
            logger.warning(f"[{tf}] Позиция уже открыта, пропускаю")
            return False

        qty = self.calculate_qty(strategy, price)
        if qty <= 0:
            logger.error(f"[{tf}] Qty = 0, не могу открыть позицию")
            self.notifier.notify_error(f"[{tf}] Не удалось рассчитать размер позиции")
            return False

        try:
            logger.info(f"[{tf}] Открываю {side} qty={qty} по рынку")
            order = self.exchange.create_order(
                symbol=self.config.symbol,
                type="market",
                side=side,
                amount=qty,
            )
            entry_price = float(order.get("average") or order.get("price") or price)
            logger.info(f"[{tf}] Ордер исполнен: {order['id']} @ {entry_price}")

            # Ставим Stop-Loss
            sl_price = self._calc_sl_price(entry_price, direction, strategy.sl_percent)
            sl_side = "sell" if direction == 1 else "buy"

            # Правильная структура для Bybit conditional order
            sl_order = self.exchange.create_order(
                symbol=self.config.symbol,
                type="market",
                side=sl_side,
                amount=qty,
                params={
                    "stopLoss": str(sl_price),  # Bybit требует строку
                    "reduceOnly": True,
                }
            )

            logger.info(f"[{tf}] Stop-Loss установлен: {sl_price} (ордер {sl_order.get('id')})")

            self.positions[tf] = {
                "side": side,
                "qty": qty,
                "entry_price": entry_price,
                "sl_order_id": sl_order.get("id"),
                "sl_price": sl_price,
                "direction": direction,
            }

            self.storage.save_open_trade(
                timeframe=tf, symbol=self.config.symbol, side=side,
                direction=direction, qty=qty, entry_price=entry_price,
                sl_price=sl_price, sl_order_id=sl_order.get("id"),
            )

            self.notifier.notify_trade("OPEN", side, entry_price, qty, sl_price=sl_price)
            logger.info(f"[{tf}] Позиция открыта: {side} {qty} @ {entry_price}, SL @ {sl_price}")
            return True

        except Exception as e:
            logger.error(f"[{tf}] Ошибка открытия позиции: {e}", exc_info=True)
            self.notifier.notify_error(f"[{tf}] open_position: {e}")
            return False

    def close_position(self, strategy: StrategyConfig) -> bool:
        tf = strategy.timeframe
        if tf not in self.positions:
            logger.warning(f"[{tf}] Нет открытой позиции для закрытия")
            return False

        pos = self.positions[tf]
        close_side = "sell" if pos["side"] == "buy" else "buy"

        try:
            # Отменяем SL ордер
            if pos.get("sl_order_id"):
                try:
                    self.exchange.cancel_order(pos["sl_order_id"], self.config.symbol)
                    logger.info(f"[{tf}] SL ордер отменён")
                except Exception as e:
                    logger.warning(f"[{tf}] Не удалось отменить SL: {e}")

            # Закрываем позицию
            logger.info(f"[{tf}] Закрываю позицию {close_side} qty={pos['qty']}")
            order = self.exchange.create_order(
                symbol=self.config.symbol,
                type="market",
                side=close_side,
                amount=pos["qty"],
                params={"reduceOnly": True},
            )
            close_price = float(order.get("average", 0))

            # PnL с учетом комиссий
            pnl = self._calculate_pnl_with_fees(
                entry_price=pos["entry_price"],
                close_price=close_price,
                qty=pos["qty"],
                side=pos["side"]
            )

            self.storage.close_trade(tf, close_price, reason="signal", pnl=pnl)

            self.notifier.notify_trade("CLOSE", close_side, close_price, pos["qty"], pnl=pnl)
            logger.info(f"[{tf}] Позиция закрыта @ {close_price}, PnL: {pnl:+.2f}")

            del self.positions[tf]
            return True

        except Exception as e:
            logger.error(f"[{tf}] Ошибка закрытия позиции: {e}", exc_info=True)
            self.notifier.notify_error(f"[{tf}] close_position: {e}")
            return False

    def check_positions_on_exchange(self):
        """Синхронизация позиций с биржей (проверка SL срабатывания)."""
        try:
            exchange_positions = self.exchange.fetch_positions([self.config.symbol])
            active_sides = set()
            for pos in exchange_positions:
                if pos["contracts"] and float(pos["contracts"]) > 0:
                    active_sides.add(pos["side"])

            # Проверяем, не закрылась ли наша позиция по SL
            for tf in list(self.positions.keys()):
                our_side = "long" if self.positions[tf]["side"] == "buy" else "short"
                if our_side not in active_sides:
                    pos = self.positions[tf]
                    sl_price = pos["sl_price"]

                    # PnL с учетом комиссий
                    pnl = self._calculate_pnl_with_fees(
                        entry_price=pos["entry_price"],
                        close_price=sl_price,
                        qty=pos["qty"],
                        side=pos["side"]
                    )

                    self.storage.close_trade(tf, sl_price, reason="sl_hit", pnl=pnl)

                    logger.info(f"[{tf}] Позиция закрыта на бирже (вероятно SL), удаляю из трекинга")
                    self.notifier.notify_trade(
                        "SL HIT", pos["side"], sl_price, pos["qty"], pnl=pnl,
                    )
                    del self.positions[tf]

        except Exception as e:
            logger.error(f"Ошибка проверки позиций: {e}", exc_info=True)

    def _recover_positions(self):
        """Восстановление позиций из БД при перезапуске."""
        db_trades = self.storage.get_open_trades()
        if not db_trades:
            logger.info("No open trades in DB to recover")
            return

        try:
            exchange_positions = self.exchange.fetch_positions([self.config.symbol])
            active_sides = {}
            for pos in exchange_positions:
                if pos["contracts"] and float(pos["contracts"]) > 0:
                    active_sides[pos["side"]] = pos
        except Exception as e:
            logger.error(f"Ошибка получения позиций с биржи при восстановлении: {e}")
            return

        for trade in db_trades:
            tf = trade["timeframe"]
            our_side = "long" if trade["side"] == "buy" else "short"

            if our_side in active_sides:
                self.positions[tf] = {
                    "side": trade["side"],
                    "qty": trade["qty"],
                    "entry_price": trade["entry_price"],
                    "sl_order_id": trade["sl_order_id"],
                    "sl_price": trade["sl_price"],
                    "direction": trade["direction"],
                }
                logger.info(f"[{tf}] Позиция восстановлена из DB: {trade['side']} @ {trade['entry_price']}")
            else:
                sl_price = trade["sl_price"] or trade["entry_price"]

                # PnL с учетом комиссий
                pnl = self._calculate_pnl_with_fees(
                    entry_price=trade["entry_price"],
                    close_price=sl_price,
                    qty=trade["qty"],
                    side=trade["side"]
                )

                self.storage.close_trade(tf, sl_price, reason="sl_hit", pnl=pnl)
                logger.info(f"[{tf}] Позиция из DB не найдена на бирже, закрыта как sl_hit")

    def _calc_sl_price(self, entry_price: float, direction: int, sl_percent: float) -> float:
        if direction == 1:  # Long — SL ниже
            return round(entry_price * (1 - sl_percent / 100), 2)
        else:  # Short — SL выше
            return round(entry_price * (1 + sl_percent / 100), 2)

    def _calculate_pnl_with_fees(
        self, entry_price: float, close_price: float, qty: float, side: str
    ) -> float:
        """
        Рассчитывает PnL с учетом комиссий Bybit.

        Args:
            entry_price: Цена входа
            close_price: Цена закрытия
            qty: Количество контрактов
            side: 'buy' или 'sell'

        Returns:
            Net PnL после вычета комиссий
        """
        # Gross PnL
        if side == "buy":
            gross_pnl = (close_price - entry_price) * qty
        else:
            gross_pnl = (entry_price - close_price) * qty

        # Комиссии за вход и выход
        entry_fee = entry_price * qty * BYBIT_TAKER_FEE
        exit_fee = close_price * qty * BYBIT_TAKER_FEE

        # Net PnL
        net_pnl = gross_pnl - entry_fee - exit_fee

        return round(net_pnl, 2)

    def _timeframe_to_seconds(self, tf: str) -> int:
        mapping = {
            "1m": 60, "3m": 180, "5m": 300, "10m": 600, "15m": 900,
            "30m": 1800, "1h": 3600, "2h": 7200, "3h": 10800, "4h": 14400,
            "6h": 21600, "8h": 28800, "12h": 43200, "1d": 86400,
        }
        return mapping.get(tf, 3600)

    def _should_check(self, strategy: StrategyConfig) -> bool:
        """Проверяем, закрылась ли новая свеча с момента последней проверки."""
        now = time.time()
        tf_seconds = self._timeframe_to_seconds(strategy.timeframe)
        last = self.last_check.get(strategy.timeframe, 0)

        # Первый запуск — всегда проверяем
        if last == 0:
            return True

        # Определяем номер текущей и предыдущей свечи
        current_candle = int(now // tf_seconds)
        last_candle = int(last // tf_seconds)

        # Новая свеча открылась (предыдущая закрылась)
        # Ждём 5 секунд после закрытия, чтобы биржа обновила данные
        if current_candle > last_candle:
            candle_start = current_candle * tf_seconds
            if (now - candle_start) >= 5:
                return True

        return False

    async def run(self):
        setup_logging(self.config.log_file)

        # Обработка Ctrl+C
        def handle_shutdown(sig, frame):
            logger.info("Получен сигнал завершения, останавливаюсь...")
            self.running = False

        signal.signal(signal.SIGINT, handle_shutdown)
        signal.signal(signal.SIGTERM, handle_shutdown)

        logger.info("=" * 50)
        logger.info("Supertrend Bot запускается")
        logger.info(f"Символ: {self.config.symbol}")
        logger.info(f"Режим: {'DEMO' if self.config.bybit_demo else 'LIVE'}")
        for s in self.config.strategies:
            logger.info(f"  Стратегия: {s.timeframe} {s.direction} ST({s.st_period},{s.st_multiplier}) SL={s.sl_percent}%")
        logger.info("=" * 50)

        # Уведомление о запуске
        self.notifier.notify_startup(self.config.strategies, self.config.bybit_demo)

        # Загружаем рынки
        self.exchange.load_markets()

        # Восстановление позиций из БД
        self._recover_positions()

        # Время последней отправки статуса
        last_status_time = 0

        while self.running:
            try:
                for strategy in self.config.strategies:
                    if not self.running:
                        break

                    if self._should_check(strategy):
                        logger.info(f"--- Проверка {strategy.timeframe} ---")
                        result = self.check_signal(strategy)

                        if result:
                            if result["action"] == "open":
                                self.open_position(strategy, result["direction"], result["price"])
                            elif result["action"] == "close":
                                self.close_position(strategy)
                            elif result["action"] == "close_and_reverse":
                                self.close_position(strategy)
                                self.open_position(strategy, result["direction"], result["price"])

                        self.last_check[strategy.timeframe] = time.time()

                # Paper trading — проверка всех 20 стратегий
                for tf in self.paper_trader.get_unique_timeframes():
                    if not self.running:
                        break
                    if self.paper_trader.should_check(tf):
                        try:
                            ohlcv = self.fetch_candles(tf)
                            self.paper_trader.process_timeframe(tf, ohlcv)
                        except Exception as e:
                            logger.error(f"[Paper:{tf}] Ошибка: {e}", exc_info=True)

                # Проверяем статус позиций на бирже
                self.check_positions_on_exchange()

                # Периодический статус в :00 и :30 (каждые 30 минут)
                now_dt = datetime.now(timezone.utc)
                minute = now_dt.minute
                if minute in (0, 30):
                    current_slot = now_dt.hour * 60 + minute
                    if current_slot != last_status_time:
                        last_status_time = current_slot
                        try:
                            balance = self.exchange.fetch_balance()
                            usdt = float(balance.get("USDT", {}).get("total", 0))
                            self.notifier.notify_status(self.positions, usdt)
                        except Exception as e:
                            logger.error(f"Ошибка отправки статуса: {e}")

                # Sleep
                await asyncio.sleep(self.config.check_interval)

            except Exception as e:
                logger.error(f"Ошибка в главном цикле: {e}", exc_info=True)
                self.notifier.notify_error(f"Main loop error: {e}")
                await asyncio.sleep(self.config.check_interval)

        logger.info("Бот остановлен")
        self.notifier.send_message("<b>Bot Stopped</b>")


def main():
    config = Config.from_env()
    errors = config.validate()
    for e in errors:
        print(f"⚠ {e}")

    if not config.bybit_api_key or not config.bybit_api_secret:
        print("ОШИБКА: API ключи Bybit не заданы в .env")
        print("Создайте файл .env по образцу .env.example")
        sys.exit(1)

    bot = SupertrendBot(config)
    asyncio.run(bot.run())


if __name__ == "__main__":
    main()
