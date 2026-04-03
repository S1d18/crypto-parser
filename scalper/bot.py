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
        self._open_positions: dict[int, dict] = {}  # trade_id -> {trade, trailing}
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

    async def tick(self):
        """One cycle: check positions -> scan -> enter.

        1. Check open positions (SL/TP/trailing)
        2. If can't trade (risk limits) -> return
        3. If already have open position -> return (one at a time)
        4. Scan market for opportunities
        5. Take best opportunity (highest strength)
        """
        # 1. Check open positions
        await self._check_open_positions()

        # 2. Risk check
        if not self._risk.can_trade():
            log.info('Risk limits reached, skipping scan')
            return

        # 3. One position at a time
        if self._open_positions:
            return

        # 4. Scan
        opportunities = await self._scanner.scan()
        if not opportunities:
            return

        # 5. Take best
        best = opportunities[0]
        await self._open_trade(best)

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

            # --- SL hit (trailing) ---
            if trailing.is_hit(price):
                reason = 'breakeven' if pos.get('breakeven_set') and \
                    abs(trailing.current_sl - entry) < abs(entry * 0.001) else 'sl'
                await self._close_trade(trade_id, price, reason)
                closed_ids.append(trade_id)
                continue

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
        """Open new trade: calc position size, save to DB, create trailing stop."""
        signal = opportunity['signal']
        symbol = opportunity['symbol']
        price = opportunity['price']

        sizing = self._risk.calc_position_size(price)

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
        """Close trade: calc PnL (with fees), update balance, save to DB.

        PnL calc:
          Long:  (exit - entry) * qty
          Short: (entry - exit) * qty
          Fees:  entry_fee + exit_fee (qty * price * taker_fee each)
          Net PnL = gross - fees
        """
        pos = self._open_positions[trade_id]
        trade = pos['trade']

        entry = trade['entry_price']
        qty = trade['qty']
        direction = trade['direction']

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
            while self._running:
                try:
                    await self.tick()
                except Exception:
                    log.error('Tick error', exc_info=True)

                await asyncio.sleep(self.cfg.scan_interval)
        except asyncio.CancelledError:
            log.info('Bot loop cancelled')
        finally:
            await self.stop()

    # ------------------------------------------------------------------
    # Status for dashboard
    # ------------------------------------------------------------------

    def get_status(self) -> dict:
        """Return current status for dashboard."""
        positions_list = []
        for tid, pos in self._open_positions.items():
            positions_list.append({
                'trade_id': tid,
                'symbol': pos['trade']['symbol'],
                'direction': pos['trade']['direction'],
                'entry_price': pos['trade']['entry_price'],
                'sl_price': pos['trade']['sl_price'],
                'tp_price': pos['trade']['tp_price'],
                'qty': pos['trade']['qty'],
            })

        return {
            'running': self._running,
            'balance': self.cfg.balance,
            'open_positions': len(self._open_positions),
            'positions': positions_list,
            'daily_stats': self._storage.get_daily_stats(),
            'all_stats': self._storage.get_all_stats(),
            'can_trade': self._risk.can_trade(),
        }
