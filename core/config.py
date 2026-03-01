import os
from dataclasses import dataclass, field
from dotenv import load_dotenv


@dataclass
class StrategyConfig:
    timeframe: str
    direction: str  # "long", "short", "both"
    st_period: int = 10
    st_multiplier: float = 3.0
    sl_percent: float = 3.0
    position_size_pct: float = 10.0  # % от баланса


@dataclass
class Config:
    # Bybit API
    bybit_api_key: str = ""
    bybit_api_secret: str = ""
    bybit_demo: bool = True

    # Telegram
    telegram_token: str = ""
    telegram_chat_id: str = ""

    # Торговый символ
    symbol: str = "BTC/USDT:USDT"

    # Стратегии по таймфреймам
    strategies: list = field(default_factory=list)

    # Интервал проверки (секунды)
    check_interval: int = 60

    # Лимит свечей для запроса
    candles_limit: int = 100

    # Максимальный размер позиции (USDT) — защита
    max_position_usdt: float = 1000.0

    # Логирование
    log_file: str = "bot.log"

    @classmethod
    def from_env(cls, env_path: str = ".env") -> "Config":
        load_dotenv(env_path)

        config = cls(
            bybit_api_key=os.getenv("BYBIT_API_KEY", ""),
            bybit_api_secret=os.getenv("BYBIT_API_SECRET", ""),
            bybit_demo=os.getenv("BYBIT_DEMO", "true").lower() == "true",
            telegram_token=os.getenv("TELEGRAM_TOKEN", ""),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
            symbol=os.getenv("SYMBOL", "BTC/USDT:USDT"),
            check_interval=int(os.getenv("CHECK_INTERVAL", "60")),
            candles_limit=int(os.getenv("CANDLES_LIMIT", "100")),
            max_position_usdt=float(os.getenv("MAX_POSITION_USDT", "1000")),
            log_file=os.getenv("LOG_FILE", "bot.log"),
        )

        # 4h Long-only
        config.strategies.append(StrategyConfig(
            timeframe="4h",
            direction="long",
            st_period=int(os.getenv("ST_PERIOD_4H", "10")),
            st_multiplier=float(os.getenv("ST_MULTIPLIER_4H", "3")),
            sl_percent=float(os.getenv("SL_PERCENT_4H", "3")),
            position_size_pct=float(os.getenv("POSITION_SIZE_4H", "10")),
        ))

        # 15m Short-only (Bybit не поддерживает 10m, ближайший — 15m)
        config.strategies.append(StrategyConfig(
            timeframe=os.getenv("SHORT_TIMEFRAME", "15m"),
            direction="short",
            st_period=int(os.getenv("ST_PERIOD_SHORT", "10")),
            st_multiplier=float(os.getenv("ST_MULTIPLIER_SHORT", "3")),
            sl_percent=float(os.getenv("SL_PERCENT_SHORT", "1")),
            position_size_pct=float(os.getenv("POSITION_SIZE_SHORT", "5")),
        ))

        return config

    def validate(self) -> list[str]:
        errors = []
        if not self.bybit_api_key:
            errors.append("BYBIT_API_KEY не задан")
        if not self.bybit_api_secret:
            errors.append("BYBIT_API_SECRET не задан")
        if not self.telegram_token:
            errors.append("TELEGRAM_TOKEN не задан (уведомления отключены)")
        if not self.telegram_chat_id:
            errors.append("TELEGRAM_CHAT_ID не задан (уведомления отключены)")
        return errors
