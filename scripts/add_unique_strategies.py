"""
Добавить 9 уникальных Supertrend конфигураций (из strategy20) в 542-стратегии.

Эти параметры отсутствуют в текущей БД:
  ST(8, 1.5)  - tight
  ST(14, 3.5) - wide
  ST(10, 2.0) - mid
  ST(20, 4.0) - xslow
  ST(12, 2.5) - mid2
  ST(8, 2.0)  - fast2
  ST(12, 4.0) - wide2
  ST(16, 3.5) - vslow
  ST(14, 4.0) - xwide

Для каждой: 5 монет × 2 направления (long + short) = 90 стратегий.
"""

import sys
from pathlib import Path
import json

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.database import Database

SYMBOLS = ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT', 'LTC/USDT:USDT', 'TON/USDT:USDT']

# 9 уникальных конфигураций ST (period, multiplier, label)
UNIQUE_PARAMS = [
    (8,  1.5, 'tight'),
    (14, 3.5, 'wide'),
    (10, 2.0, 'mid'),
    (20, 4.0, 'xslow'),
    (12, 2.5, 'mid2'),
    (8,  2.0, 'fast2'),
    (12, 4.0, 'wide2'),
    (16, 3.5, 'vslow'),
    (14, 4.0, 'xwide'),
]

# Таймфреймы на которых работают эти конфигурации (оригинал из strategy20)
# Но для 542 добавляем на ВСЕ основные таймфреймы
TIMEFRAMES = ['5m', '15m', '30m', '1h', '2h', '4h', '6h', '12h', '1d']


def calculate_sl_percent(timeframe: str) -> float:
    sl_map = {
        '1m': 0.5, '3m': 0.75, '5m': 1.0,
        '15m': 1.0, '30m': 1.5,
        '1h': 2.0, '2h': 2.5,
        '4h': 3.0, '6h': 3.0,
        '12h': 3.5, '1d': 4.0
    }
    return sl_map.get(timeframe, 2.0)


def main():
    print("=" * 60)
    print("Добавление 9 уникальных Supertrend конфигураций")
    print("=" * 60)

    db = Database()

    inserted = 0
    skipped = 0

    for tf in TIMEFRAMES:
        for symbol in SYMBOLS:
            coin = symbol.split('/')[0].lower()

            for period, multiplier, label in UNIQUE_PARAMS:
                for direction in ['long', 'short']:
                    name = f'supertrend_{coin}_{tf}_{label}_{direction}'
                    params = json.dumps({
                        'st_period': period,
                        'st_multiplier': multiplier,
                    })

                    try:
                        db.create_strategy(
                            name=name,
                            type='supertrend',
                            category='paper',
                            symbol=symbol,
                            timeframe=tf,
                            direction=direction,
                            leverage=1,
                            params=params,
                            status='stopped',
                        )
                        inserted += 1
                    except Exception as e:
                        if "UNIQUE constraint" in str(e):
                            skipped += 1
                        else:
                            print(f"  ERROR: {name}: {e}")

    total = db.conn.execute("SELECT COUNT(*) FROM strategies").fetchone()[0]

    print(f"\nДобавлено: {inserted}")
    print(f"Уже существовали: {skipped}")
    print(f"Всего стратегий в БД: {total}")
    print("=" * 60)


if __name__ == "__main__":
    main()
