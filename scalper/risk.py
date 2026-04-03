from __future__ import annotations

from datetime import datetime, timedelta
from scalper.config import Config


class TrailingStop:
    def __init__(self, direction: str, entry: float, sl: float):
        self.direction = direction
        self.current_sl = sl
        self.distance = abs(entry - sl)

    def update(self, current_price: float) -> float:
        """Update trailing stop. Returns new SL.
        Long: new_sl = price - distance. Only moves UP.
        Short: new_sl = price + distance. Only moves DOWN."""
        if self.direction == "long":
            new_sl = current_price - self.distance
            if new_sl > self.current_sl:
                self.current_sl = new_sl
        else:
            new_sl = current_price + self.distance
            if new_sl < self.current_sl:
                self.current_sl = new_sl
        return self.current_sl

    def is_hit(self, current_price: float) -> bool:
        """Long: price <= sl. Short: price >= sl."""
        if self.direction == "long":
            return current_price <= self.current_sl
        return current_price >= self.current_sl


class RiskManager:
    def __init__(self, config: Config):
        self.config = config
        self.consecutive_losses: int = 0
        self.daily_pnl: float = 0.0
        self.pause_until: datetime | None = None
        self.last_reset_date = datetime.now().date()

    def calc_position_size(self, price: float) -> dict:
        """Returns {'qty': float, 'margin': float, 'position_value': float}"""
        margin = self.config.balance * self.config.max_risk_per_trade
        position_value = margin * self.config.leverage
        qty = position_value / price
        return {
            'qty': qty,
            'margin': margin,
            'position_value': position_value,
        }

    def record_loss(self) -> None:
        self.consecutive_losses += 1

    def record_win(self) -> None:
        self.consecutive_losses = 0

    def record_daily_pnl(self, pnl: float) -> None:
        self.daily_pnl += pnl

    def reset_daily(self) -> None:
        self.daily_pnl = 0.0
        self.consecutive_losses = 0
        self.last_reset_date = datetime.now().date()

    def should_pause(self) -> bool:
        """True if in pause period or consecutive losses >= max.
        When threshold hit: set pause_until = now + pause_minutes, reset counter."""
        now = datetime.now()
        if self.pause_until and now < self.pause_until:
            return True
        if self.consecutive_losses >= self.config.max_consecutive_losses:
            self.pause_until = now + timedelta(minutes=self.config.pause_after_losses_minutes)
            self.consecutive_losses = 0
            return True
        return False

    def is_daily_limit_hit(self) -> bool:
        """True if daily_pnl <= -max_daily_loss"""
        return self.daily_pnl <= -self.config.max_daily_loss

    def can_trade(self) -> bool:
        """Auto-resets daily stats on new day. Returns not paused and not daily limit."""
        today = datetime.now().date()
        if today != self.last_reset_date:
            self.reset_daily()
        return not self.should_pause() and not self.is_daily_limit_hit()

    def create_trailing_stop(self, direction: str, entry: float, sl: float) -> TrailingStop:
        return TrailingStop(direction, entry, sl)
