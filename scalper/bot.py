"""Main ScalperBot — asyncio trading loop orchestrator."""

from __future__ import annotations

import asyncio
import logging

from scalper.config import Config
from scalper.exchange import Exchange
from scalper.scanner import Scanner
from scalper.signals import SignalEngine
from scalper.risk import RiskManager, TrailingStop
from scalper.storage import Storage
from scalper.market_data import MarketData

log = logging.getLogger(__name__)


class ScalperBot:
    """Core trading bot that ties exchange, scanner, risk and storage together."""

    def __init__(self, config: Config):
        self.cfg = config
        self._exchange = Exchange(config)
        self._scanner = Scanner(config, exchange=self._exchange)
        self._risk = RiskManager(config)
        self._storage = Storage()
        self._signal_engine = SignalEngine(config)
        self._market_data = MarketData(self._exchange)
        self._open_positions: dict[int, dict] = {}  # trade_id -> {trade, trailing}
        self._last_prices: dict[str, float] = {}    # symbol -> last known price
        self._running = False
        self._callbacks: list = []

    # ------------------------------------------------------------------
    # Callbacks for websocket / dashboard notifications
    # ------------------------------------------------------------------

    def on_update(self, callback):
        """Subscribe to updates (for web dashboard)."""
        self._callbacks.append(callback)

    def _notify(self, event: str, data: dict):
        """Call all registered callbacks."""
        for cb in self._callbacks:
            try:
                cb(event, data)
            except Exception:
                log.warning('Callback error for event %s', event, exc_info=True)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self):
        """Start exchange, recover balance and open positions from DB."""
        await self._exchange.start()
        self._running = True

        # Restore balance from DB (survives restarts)
        saved_balance = self._storage.get_state('balance')
        if saved_balance is not None:
            self.cfg.balance = float(saved_balance)
            log.info('Restored balance from DB: $%.2f', self.cfg.balance)

        # Recover open positions
        open_trades = self._storage.get_open_trades()
        for trade in open_trades:
            trailing = self._risk.create_trailing_stop(
                direction=trade['direction'],
                entry=trade['entry_price'],
                sl=trade['sl_price'],
            )
            self._open_positions[trade['id']] = {
                'trade': trade,
                'trailing': trailing,
            }

        log.info(
            'Bot started. Balance=%.2f, recovered %d open positions',
            self.cfg.balance, len(self._open_positions),
        )
        self._notify('started', {'balance': self.cfg.balance})

    async def stop(self):
        """Stop bot, close exchange and storage."""
        self._running = False
        await self._exchange.close()
        self._storage.close()
        log.info('Bot stopped')
        self._notify('stopped', {})

    # ------------------------------------------------------------------
    # Main tick
    # ------------------------------------------------------------------

    async def tick_positions(self):
        """Fast tick: check open positions (SL/TP/trailing/signals).
        Called every 2 seconds — priority on protecting open trades."""
        if self._open_positions:
            await self._check_open_positions()

    async def tick_scan(self):
        """Slow tick: scan market for new entries.
        Called every scan_interval seconds."""
        if not self._risk.can_trade():
            log.info('Risk limits reached, skipping scan')
            return

        max_pos = self.cfg.max_open_positions
        open_count = len(self._open_positions)
        if open_count >= max_pos:
            return

        opportunities = await self._scanner.scan()
        if not opportunities:
            return

        held_symbols = {pos['trade']['symbol'] for pos in self._open_positions.values()}
        slots = max_pos - open_count

        for opp in opportunities:
            if slots <= 0:
                break
            if opp['symbol'] in held_symbols:
                continue
            await self._open_trade(opp)
            held_symbols.add(opp['symbol'])
            slots -= 1

    async def tick(self):
        """Combined tick for backwards compatibility (used in tests)."""
        await self.tick_positions()
        await self.tick_scan()

    # ------------------------------------------------------------------
    # Position management
    # ------------------------------------------------------------------

    async def _check_open_positions(self):
        """For each open position: get price, update trailing, check TP/SL/signal/breakeven."""
        closed_ids = []

        for trade_id, pos in self._open_positions.items():
            trade = pos['trade']
            trailing: TrailingStop = pos['trailing']

            try:
                price = await self._exchange.get_price(trade['symbol'])
                self._last_prices[trade['symbol']] = price
            except Exception:
                log.warning('Failed to get price for %s', trade['symbol'], exc_info=True)
                continue

            # Update trailing stop
            trailing.update(price)

            direction = trade['direction']
            entry = trade['entry_price']
            tp = trade['tp_price']

            # --- Безубыток: цена прошла 50% к TP → SL на вход ---
            if not pos.get('breakeven_set'):
                halfway = entry + (tp - entry) * 0.5 if direction == 'long' \
                    else entry - (entry - tp) * 0.5
                be_hit = (direction == 'long' and price >= halfway) or \
                         (direction == 'short' and price <= halfway)
                if be_hit:
                    trailing.current_sl = entry
                    pos['breakeven_set'] = True
                    log.info('Breakeven set for #%d %s @ %.4f (SL moved to entry %.4f)',
                             trade_id, trade['symbol'], price, entry)

            # --- TP hit ---
            tp_hit = (direction == 'long' and price >= tp) or \
                     (direction == 'short' and price <= tp)
            if tp_hit:
                await self._close_trade(trade_id, price, 'tp')
                closed_ids.append(trade_id)
                continue

            # --- Умная фиксация: PnL >= min_profit и цена начала откатывать ---
            qty = trade['qty']
            margin = trade.get('margin', entry * qty / self.cfg.leverage)
            if direction == 'long':
                pnl_now = (price - entry) * qty
            else:
                pnl_now = (entry - price) * qty
            fees = (entry * qty + price * qty) * self.cfg.taker_fee
            net_pnl = pnl_now - fees

            # Отслеживаем пиковый PnL
            peak_key = f'peak_pnl_{trade_id}'
            peak_pnl = pos.get(peak_key, 0)
            if net_pnl > peak_pnl:
                pos[peak_key] = net_pnl
                peak_pnl = net_pnl

            # Если PnL был >= min_profit и откатил на 30% от пика → забираем
            if peak_pnl >= self.cfg.min_profit_usd and net_pnl > 0:
                pullback = (peak_pnl - net_pnl) / peak_pnl if peak_pnl > 0 else 0
                if pullback >= 0.3:
                    log.info('Smart take profit #%d %s: peak=$%.2f, now=$%.2f, pullback=%.0f%%',
                             trade_id, trade['symbol'], peak_pnl, net_pnl, pullback * 100)
                    await self._close_trade(trade_id, price, 'smart_tp')
                    closed_ids.append(trade_id)
                    continue

            # --- SL hit (trailing) ---
            if trailing.is_hit(price):
                reason = 'breakeven' if pos.get('breakeven_set') and \
                    abs(trailing.current_sl - entry) < abs(entry * 0.001) else 'sl'
                await self._close_trade(trade_id, price, reason)
                closed_ids.append(trade_id)
                continue

            # --- Market data: стакан, funding, OI ---
            try:
                mkt = await self._market_data.get_exit_signals(trade['symbol'], direction)
                if mkt['should_exit'] and net_pnl > 0:
                    log.info('Market exit #%d %s: score=%.2f reasons=%s pnl=$%.2f',
                             trade_id, trade['symbol'], mkt['score'],
                             mkt['reasons'], net_pnl)
                    await self._close_trade(trade_id, price, 'market_signal')
                    closed_ids.append(trade_id)
                    continue
                elif mkt['tighten_sl']:
                    # Подтянуть стоп на 50% ближе к текущей цене
                    old_sl = trailing.current_sl
                    if direction == 'long':
                        new_sl = price - (price - old_sl) * 0.5
                        if new_sl > old_sl:
                            trailing.current_sl = new_sl
                            log.info('Tightened SL #%d %s: %.4f → %.4f (market pressure)',
                                     trade_id, trade['symbol'], old_sl, new_sl)
                    else:
                        new_sl = price + (old_sl - price) * 0.5
                        if new_sl < old_sl:
                            trailing.current_sl = new_sl
                            log.info('Tightened SL #%d %s: %.4f → %.4f (market pressure)',
                                     trade_id, trade['symbol'], old_sl, new_sl)
            except Exception:
                log.debug('Market data check failed for %s', trade['symbol'], exc_info=True)

            # --- Закрытие по сигналу разворота индикаторов ---
            try:
                ohlcv = await self._exchange.fetch_ohlcv(
                    trade['symbol'], self.cfg.scalp_timeframe, limit=100)
                signal = self._signal_engine.evaluate(ohlcv)
                if signal and signal.direction != direction:
                    log.info('Signal reversal for #%d %s: was %s, now %s',
                             trade_id, trade['symbol'], direction, signal.direction)
                    await self._close_trade(trade_id, price, 'signal_reversal')
                    closed_ids.append(trade_id)
                    continue
            except Exception:
                log.debug('Could not check signal reversal for %s', trade['symbol'],
                          exc_info=True)

        # Remove closed positions
        for tid in closed_ids:
            del self._open_positions[tid]

    async def _open_trade(self, opportunity: dict):
        """Open new trade: place real order on exchange, save to DB."""
        signal = opportunity['signal']
        symbol = opportunity['symbol']
        price = opportunity['price']

        sizing = self._risk.calc_position_size(price)

        # Place real order on exchange
        try:
            order = await self._exchange.open_position(
                symbol=symbol,
                direction=signal.direction,
                qty=sizing['qty'],
                leverage=self.cfg.leverage,
            )
            # Use actual fill price if available
            fill_price = order.get('average') or order.get('price') or price
            if fill_price:
                price = float(fill_price)
            # Use actual filled qty
            filled_qty = order.get('filled') or sizing['qty']
            if filled_qty:
                sizing['qty'] = float(filled_qty)
        except Exception as e:
            log.error('Failed to open %s %s: %s', signal.direction, symbol, e)
            return

        trade_id = self._storage.open_trade(
            symbol=symbol,
            direction=signal.direction,
            qty=sizing['qty'],
            entry_price=price,
            sl_price=signal.sl_price,
            tp_price=signal.tp_price,
            leverage=self.cfg.leverage,
            margin=sizing['margin'],
            reasons=', '.join(signal.reasons),
        )

        trailing = self._risk.create_trailing_stop(
            direction=signal.direction,
            entry=price,
            sl=signal.sl_price,
        )

        trade = {
            'id': trade_id,
            'symbol': symbol,
            'direction': signal.direction,
            'qty': sizing['qty'],
            'entry_price': price,
            'sl_price': signal.sl_price,
            'tp_price': signal.tp_price,
            'leverage': self.cfg.leverage,
            'margin': sizing['margin'],
        }

        self._open_positions[trade_id] = {
            'trade': trade,
            'trailing': trailing,
        }

        log.info(
            'Opened %s %s @ %.4f | SL=%.4f TP=%.4f | qty=%.4f',
            signal.direction.upper(), symbol, price,
            signal.sl_price, signal.tp_price, sizing['qty'],
        )
        self._notify('trade_opened', trade)

    async def _close_trade(self, trade_id: int, exit_price: float, reason: str):
        """Close trade: place close order, calc PnL, update balance, save to DB."""
        pos = self._open_positions[trade_id]
        trade = pos['trade']

        entry = trade['entry_price']
        qty = trade['qty']
        direction = trade['direction']

        # Place real close order on exchange
        try:
            order = await self._exchange.close_position(
                symbol=trade['symbol'],
                direction=direction,
                qty=qty,
            )
            # Use actual fill price
            fill_price = order.get('average') or order.get('price')
            if fill_price:
                exit_price = float(fill_price)
        except Exception as e:
            log.error('Failed to close #%d %s: %s', trade_id, trade['symbol'], e)
            return

        # Gross PnL
        if direction == 'long':
            gross_pnl = (exit_price - entry) * qty
        else:
            gross_pnl = (entry - exit_price) * qty

        # Fees
        entry_fee = qty * entry * self.cfg.taker_fee
        exit_fee = qty * exit_price * self.cfg.taker_fee
        total_fees = entry_fee + exit_fee

        net_pnl = gross_pnl - total_fees

        # PnL percent relative to margin
        margin = trade['margin']
        pnl_pct = (net_pnl / margin * 100) if margin > 0 else 0.0

        # Update balance
        self.cfg.balance += net_pnl

        # Record in risk manager
        self._risk.record_daily_pnl(net_pnl)
        if net_pnl >= 0:
            self._risk.record_win()
        else:
            self._risk.record_loss()

        # Save to DB
        self._storage.close_trade(
            trade_id=trade_id,
            exit_price=exit_price,
            pnl=net_pnl,
            pnl_pct=pnl_pct,
            close_reason=reason,
        )

        # Save equity snapshot and persist balance
        self._storage.save_equity_snapshot(self.cfg.balance)
        self._storage.save_state('balance', str(self.cfg.balance))

        log.info(
            'Closed trade #%d %s | reason=%s | PnL=%.2f (%.1f%%)',
            trade_id, trade['symbol'], reason, net_pnl, pnl_pct,
        )
        self._notify('trade_closed', {
            'trade_id': trade_id,
            'symbol': trade['symbol'],
            'direction': direction,
            'pnl': net_pnl,
            'pnl_pct': pnl_pct,
            'reason': reason,
        })

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def run(self):
        """Main loop: start(), then tick() every scan_interval seconds."""
        # Retry exchange connection with backoff
        for attempt in range(1, 6):
            try:
                await self.start()
                break
            except Exception:
                wait = min(attempt * 10, 60)
                log.warning('Exchange connection failed (attempt %d/5), retry in %ds',
                            attempt, wait, exc_info=True)
                if attempt == 5:
                    log.error('Could not connect to exchange after 5 attempts. '
                              'Bot will run without trading until reconnected.')
                    self._running = True
                else:
                    await asyncio.sleep(wait)

        try:
            # Two parallel loops: fast (positions) + slow (scanning)
            await asyncio.gather(
                self._loop_positions(),
                self._loop_scan(),
            )
        except asyncio.CancelledError:
            log.info('Bot loop cancelled')
        finally:
            await self.stop()

    async def _loop_positions(self):
        """Fast loop: check open positions every 2 seconds."""
        while self._running:
            try:
                await self.tick_positions()
            except Exception:
                log.error('Position tick error', exc_info=True)
            await asyncio.sleep(2)

    async def _loop_scan(self):
        """Slow loop: scan for new entries every scan_interval seconds."""
        while self._running:
            try:
                await self.tick_scan()
            except Exception:
                log.error('Scan tick error', exc_info=True)
            await asyncio.sleep(self.cfg.scan_interval)

    # ------------------------------------------------------------------
    # Status for dashboard
    # ------------------------------------------------------------------

    def get_status(self) -> dict:
        """Return current status for dashboard."""
        positions_list = []
        total_unrealized = 0.0

        for tid, pos in self._open_positions.items():
            trade = pos['trade']
            symbol = trade['symbol']
            entry = trade['entry_price']
            qty = trade['qty']
            direction = trade['direction']
            margin = trade.get('margin', entry * qty / self.cfg.leverage)

            current_price = self._last_prices.get(symbol, entry)

            # Unrealized PnL
            if direction == 'long':
                pnl_gross = (current_price - entry) * qty
            else:
                pnl_gross = (entry - current_price) * qty
            fees = (entry * qty + current_price * qty) * self.cfg.taker_fee
            pnl = pnl_gross - fees
            pnl_pct = (pnl / margin * 100) if margin > 0 else 0.0
            total_unrealized += pnl

            positions_list.append({
                'trade_id': tid,
                'symbol': symbol,
                'direction': direction,
                'entry_price': entry,
                'current_price': float(current_price),
                'sl_price': trade['sl_price'],
                'tp_price': trade['tp_price'],
                'qty': qty,
                'margin': round(margin, 2),
                'pnl': round(pnl, 2),
                'pnl_pct': round(pnl_pct, 2),
            })

        return {
            'running': self._running,
            'balance': self.cfg.balance,
            'unrealized_pnl': round(total_unrealized, 2),
            'total_balance': round(self.cfg.balance + total_unrealized, 2),
            'open_positions': len(self._open_positions),
            'positions': positions_list,
            'daily_stats': self._storage.get_daily_stats(),
            'all_stats': self._storage.get_all_stats(),
            'can_trade': self._risk.can_trade(),
        }
