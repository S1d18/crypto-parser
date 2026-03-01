"""
Кэш для OHLCV данных - избегает дублирующих запросов к API.

Если 10 стратегий используют BTC/USDT 5m, делается ОДИН запрос вместо 10.
"""
import time
from typing import Dict, List, Tuple, Optional
from threading import Lock
from datetime import datetime, timedelta


    # TTL по таймфреймам — чем длиннее свеча, тем дольше кэш
TIMEFRAME_TTL = {
    '1m': 30, '3m': 60, '5m': 60,
    '15m': 120, '30m': 180,
    '1h': 300, '2h': 300,
    '4h': 600, '6h': 600,
    '12h': 1800, '1d': 3600,
}


class OHLCVCache:
    """Thread-safe кэш для OHLCV данных."""

    def __init__(self, ttl_seconds: int = 60):
        """
        Args:
            ttl_seconds: время жизни кэша в секундах (по умолчанию 60 сек)
        """
        self.cache: Dict[str, Dict] = {}  # {key: {data, timestamp}}
        self.lock = Lock()
        self.ttl_seconds = ttl_seconds

    def _make_key(self, symbol: str, timeframe: str) -> str:
        """Создать ключ кэша."""
        return f"{symbol}:{timeframe}"

    def get(self, symbol: str, timeframe: str) -> Optional[List]:
        """
        Получить OHLCV из кэша если не устарел.
        TTL зависит от таймфрейма: 1m=30s, 1h=5min, 1d=60min.

        Returns:
            List[List] если в кэше и не устарел, иначе None
        """
        key = self._make_key(symbol, timeframe)

        with self.lock:
            if key not in self.cache:
                return None

            cached = self.cache[key]
            age = time.time() - cached['timestamp']

            # TTL зависит от таймфрейма
            ttl = TIMEFRAME_TTL.get(timeframe, self.ttl_seconds)

            if age > ttl:
                del self.cache[key]
                return None

            return cached['data']

    def set(self, symbol: str, timeframe: str, data: List):
        """Сохранить OHLCV в кэш."""
        key = self._make_key(symbol, timeframe)

        with self.lock:
            self.cache[key] = {
                'data': data,
                'timestamp': time.time()
            }

    def clear_expired(self):
        """Удалить устаревшие записи из кэша."""
        now = time.time()

        with self.lock:
            expired_keys = [
                key for key, value in self.cache.items()
                if now - value['timestamp'] > self.ttl_seconds
            ]

            for key in expired_keys:
                del self.cache[key]

    def get_stats(self) -> Dict:
        """Получить статистику кэша."""
        with self.lock:
            return {
                'size': len(self.cache),
                'keys': list(self.cache.keys())
            }


# Глобальный singleton instance
_ohlcv_cache_instance: Optional[OHLCVCache] = None


def get_ohlcv_cache() -> OHLCVCache:
    """Получить глобальный экземпляр OHLCV кэша."""
    global _ohlcv_cache_instance
    if _ohlcv_cache_instance is None:
        _ohlcv_cache_instance = OHLCVCache(ttl_seconds=60)
    return _ohlcv_cache_instance
