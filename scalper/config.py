from __future__ import annotations

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv() -> None:  # type: ignore[misc]
        pass


@dataclass
class Config:
    # Bybit API
    bybit_api_key: str = ''
    bybit_api_secret: str = ''
    bybit_demo: bool = True

    # Balance and positions
    balance: float = 200.0
    leverage: int = 20
    max_risk_per_trade: float = 0.5
    max_open_positions: int = 3

    # Risk management
    max_daily_loss: float = 30.0
    max_consecutive_losses: int = 10
    pause_after_losses_minutes: int = 60

    # Scanning
    scan_interval: int = 30
    scalp_timeframe: str = '3m'
    trend_timeframe: str = '15m'
    top_n_coins: int = 50

    # Bybit fee
    taker_fee: float = 0.00055

    # Indicators
    atr_sl_multiplier: float = 1.5
    tp_ratio: float = 2.0
    adx_min: int = 20
    ema_fast: int = 9
    ema_slow: int = 21
    rsi_period: int = 14
    rsi_oversold: int = 35
    rsi_overbought: int = 65
    atr_period: int = 14
    adx_period: int = 14
    volume_ma_period: int = 20

    # Web
    web_port: int = 5001

    @classmethod
    def from_env(cls) -> Config:
        """Load config from environment variables (with dotenv support)."""
        load_dotenv()

        def _bool(val: str) -> bool:
            return val.lower() in ('true', '1', 'yes')

        return cls(
            bybit_api_key=os.getenv('BYBIT_API_KEY', ''),
            bybit_api_secret=os.getenv('BYBIT_API_SECRET', ''),
            bybit_demo=_bool(os.getenv('BYBIT_DEMO', 'true')),
            balance=float(os.getenv('BALANCE', '200.0')),
            leverage=int(os.getenv('LEVERAGE', '20')),
            max_daily_loss=float(os.getenv('MAX_DAILY_LOSS', '30.0')),
            max_consecutive_losses=int(os.getenv('MAX_CONSECUTIVE_LOSSES', '10')),
            scan_interval=int(os.getenv('SCAN_INTERVAL', '30')),
            scalp_timeframe=os.getenv('SCALP_TIMEFRAME', '3m'),
            top_n_coins=int(os.getenv('TOP_N_COINS', '50')),
            web_port=int(os.getenv('WEB_PORT', '5001')),
            max_open_positions=int(os.getenv('MAX_OPEN_POSITIONS', '3')),
        )
