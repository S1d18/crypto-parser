import logging
from datetime import datetime, timezone

import requests

logger = logging.getLogger(__name__)


class TelegramNotifier:
    BASE_URL = "https://api.telegram.org/bot{token}/sendMessage"

    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id
        self.enabled = bool(token and chat_id)
        if not self.enabled:
            logger.warning("Telegram уведомления отключены (token или chat_id не заданы)")

    def send_message(self, text: str) -> bool:
        if not self.enabled:
            logger.info(f"[TG OFF] {text}")
            return False
        try:
            resp = requests.post(
                self.BASE_URL.format(token=self.token),
                json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                },
                timeout=10,
            )
            if resp.status_code != 200:
                logger.error(f"Telegram API error: {resp.status_code} {resp.text}")
                return False
            return True
        except Exception as e:
            logger.error(f"Telegram send error: {e}")
            return False

    def notify_startup(self, strategies: list, demo: bool) -> bool:
        mode = "DEMO" if demo else "LIVE"
        lines = [f"<b>Bot Started [{mode}]</b>"]
        lines.append(f"Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
        for s in strategies:
            lines.append(f"  {s.timeframe} {s.direction.upper()} | SL={s.sl_percent}% | Size={s.position_size_pct}%")
        return self.send_message("\n".join(lines))

    def notify_signal(self, timeframe: str, direction: int, price: float, changed: bool) -> bool:
        dir_str = "UP (Long)" if direction == 1 else "DOWN (Short)"
        status = "SIGNAL CHANGE" if changed else "Signal"
        emoji = "🔴" if direction == -1 else "🟢"
        text = (
            f"<b>{emoji} {status} [{timeframe}]</b>\n"
            f"Supertrend: {dir_str}\n"
            f"Price: {price:,.2f}"
        )
        return self.send_message(text)

    def notify_trade(self, action: str, side: str, price: float, qty: float, sl_price: float = None, pnl: float = None) -> bool:
        lines = [f"<b>{'📈' if side == 'buy' else '📉'} {action.upper()} {side.upper()}</b>"]
        lines.append(f"Price: {price:,.2f}")
        lines.append(f"Qty: {qty}")
        if sl_price:
            lines.append(f"SL: {sl_price:,.2f}")
        if pnl is not None:
            lines.append(f"PnL: {pnl:+,.2f} USDT")
        return self.send_message("\n".join(lines))

    def notify_error(self, error: str) -> bool:
        text = f"<b>⚠️ ERROR</b>\n{error}"
        return self.send_message(text)

    def notify_status(self, positions: dict, balance: float) -> bool:
        lines = [
            "<b>📊 Status Report</b>",
            f"Balance: {balance:,.2f} USDT",
        ]
        if positions:
            for tf, pos in positions.items():
                lines.append(f"  {tf}: {pos['side']} qty={pos['qty']} entry={pos['entry_price']:,.2f}")
        else:
            lines.append("  No open positions")
        lines.append(f"Time: {datetime.now(timezone.utc).strftime('%H:%M UTC')}")
        return self.send_message("\n".join(lines))
