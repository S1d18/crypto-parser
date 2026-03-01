"""
Генератор 100+ торговых стратегий.

Создает стратегии на основе различных индикаторов и параметров:
- 50+ Supertrend (разные таймфреймы, периоды, множители)
- 20+ RSI
- 15+ MACD
- 10+ Bollinger Bands
- 5+ EMA Crossover

Все стратегии сохраняются в БД для управления через веб-интерфейс.
"""

import sys
from pathlib import Path
import json

# Добавить корень проекта в PYTHONPATH
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.database import Database

# Константы
TIMEFRAMES = ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '12h', '1d']
DIRECTIONS = ['long', 'short', 'both']
SYMBOLS = ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT', 'LTC/USDT:USDT', 'TON/USDT:USDT']

# Параметры Supertrend
SUPERTREND_PARAMS = [
    (7, 2.0), (7, 2.5), (7, 3.0), (7, 3.5),
    (10, 2.0), (10, 2.5), (10, 3.0), (10, 3.5),
    (14, 2.0), (14, 2.5), (14, 3.0), (14, 3.5),
    (20, 2.0), (20, 2.5), (20, 3.0)
]

# Параметры RSI
RSI_PARAMS = [
    (14, 30, 70),  # (период, oversold, overbought)
    (14, 25, 75),
    (14, 20, 80),
    (21, 30, 70),
    (21, 25, 75),
    (7, 30, 70),
    (7, 25, 75)
]

# Параметры MACD
MACD_PARAMS = [
    (12, 26, 9),  # (fast, slow, signal)
    (8, 17, 9),
    (5, 13, 5),
    (12, 24, 6),
    (16, 32, 12)
]


def calculate_sl_percent(timeframe: str) -> float:
    """Рассчитать SL% на основе таймфрейма."""
    sl_map = {
        '1m': 0.5, '3m': 0.75, '5m': 1.0,
        '15m': 1.0, '30m': 1.5,
        '1h': 2.0, '2h': 2.5,
        '4h': 3.0, '6h': 3.0,
        '12h': 3.5, '1d': 4.0
    }
    return sl_map.get(timeframe, 2.0)


def get_group(timeframe: str) -> str:
    """Определить группу стратегии по таймфрейму."""
    if timeframe in ['1m', '3m', '5m', '15m']:
        return 'scalping'
    elif timeframe in ['30m', '1h']:
        return 'intraday'
    elif timeframe in ['2h', '4h', '6h']:
        return 'swing'
    else:  # 12h, 1d
        return 'position'


def get_symbols_for_timeframe(timeframe: str) -> list:
    """Получить список символов для таймфрейма - ВСЕ 5 МОНЕТ для всех TF."""
    # Пользователь хочет ВСЕ монеты на ВСЕХ таймфреймах
    return SYMBOLS


def generate_supertrend_strategies():
    """Генерировать 50+ Supertrend стратегий для разных монет."""
    strategies = []

    # Для каждого таймфрейма создаем несколько вариантов
    for tf in TIMEFRAMES:
        sl_percent = calculate_sl_percent(tf)
        group = get_group(tf)
        symbols = get_symbols_for_timeframe(tf)

        # Выбираем 3 набора параметров для каждого таймфрейма
        selected_params = [
            (7, 2.0),   # fast
            (10, 3.0),  # standard
            (14, 3.0),  # slow
        ]

        for symbol in symbols:
            # Короткий префикс монеты (BTC, ETH, SOL, LTC, TON)
            coin = symbol.split('/')[0].lower()

            for period, multiplier in selected_params:
                param_label = 'fast' if period == 7 else 'std' if period == 10 else 'slow'

                # Long стратегия
                strategies.append({
                    'name': f'supertrend_{coin}_{tf}_{param_label}_long',
                    'type': 'supertrend',
                    'category': 'paper',
                    'symbol': symbol,
                    'timeframe': tf,
                    'direction': 'long',
                    'leverage': 1,
                    'params': json.dumps({
                        'st_period': period,
                        'st_multiplier': multiplier
                    }),
                    'sl_percent': sl_percent,
                    'status': 'stopped',
                    'group': group
                })

                # Short стратегия
                strategies.append({
                    'name': f'supertrend_{coin}_{tf}_{param_label}_short',
                    'type': 'supertrend',
                    'category': 'paper',
                    'symbol': symbol,
                    'timeframe': tf,
                    'direction': 'short',
                    'leverage': 1,
                    'params': json.dumps({
                        'st_period': period,
                        'st_multiplier': multiplier
                    }),
                    'sl_percent': sl_percent,
                    'status': 'stopped',
                    'group': group
                })

    return strategies


def generate_rsi_strategies():
    """Генерировать 30+ RSI стратегий для разных монет."""
    strategies = []

    # Больше таймфреймов для RSI
    rsi_timeframes = ['1m', '5m', '15m', '30m', '1h', '2h', '4h', '1d']

    for tf in rsi_timeframes:
        sl_percent = calculate_sl_percent(tf)
        group = get_group(tf)
        symbols = get_symbols_for_timeframe(tf)

        # 3 набора параметров для каждого таймфрейма
        selected_params = [
            (14, 30, 70),  # standard
            (14, 20, 80),  # wide
            (7, 30, 70),   # fast
        ]

        for symbol in symbols:
            coin = symbol.split('/')[0].lower()

            for period, oversold, overbought in selected_params:
                param_label = 'std' if period == 14 and oversold == 30 else 'wide' if oversold == 20 else 'fast'

                strategies.append({
                    'name': f'rsi_{coin}_{tf}_{param_label}',
                    'type': 'rsi',
                    'category': 'paper',
                    'symbol': symbol,
                    'timeframe': tf,
                    'direction': 'both',
                    'leverage': 1,
                    'params': json.dumps({
                        'rsi_period': period,
                        'rsi_oversold': oversold,
                        'rsi_overbought': overbought
                    }),
                    'sl_percent': sl_percent,
                    'status': 'stopped',
                    'group': group
                })

    return strategies


def generate_macd_strategies():
    """Генерировать 20+ MACD стратегий для разных монет."""
    strategies = []

    macd_timeframes = ['5m', '15m', '30m', '1h', '4h', '1d']

    for tf in macd_timeframes:
        sl_percent = calculate_sl_percent(tf)
        group = get_group(tf)
        symbols = get_symbols_for_timeframe(tf)

        # 3 набора параметров
        selected_params = [
            (12, 26, 9),  # standard
            (8, 17, 9),   # fast
            (5, 13, 5),   # very fast
        ]

        for symbol in symbols:
            coin = symbol.split('/')[0].lower()

            for fast, slow, signal in selected_params:
                param_label = 'std' if fast == 12 else 'fast' if fast == 8 else 'vfast'

                strategies.append({
                    'name': f'macd_{coin}_{tf}_{param_label}',
                    'type': 'macd',
                    'category': 'paper',
                    'symbol': symbol,
                    'timeframe': tf,
                    'direction': 'both',
                    'leverage': 1,
                    'params': json.dumps({
                        'macd_fast': fast,
                        'macd_slow': slow,
                        'macd_signal': signal
                    }),
                    'sl_percent': sl_percent,
                    'status': 'stopped',
                    'group': group
                })

    return strategies


def main():
    """Главная функция."""
    print("=" * 60)
    print("Генератор торговых стратегий")
    print("=" * 60)

    # Генерация стратегий
    print("\nГенерация стратегий...")
    supertrend = generate_supertrend_strategies()
    rsi = generate_rsi_strategies()
    macd = generate_macd_strategies()

    all_strategies = supertrend + rsi + macd

    print(f"[OK] Supertrend: {len(supertrend)} стратегий")
    print(f"[OK] RSI: {len(rsi)} стратегий")
    print(f"[OK] MACD: {len(macd)} стратегий")
    print(f"\nВсего: {len(all_strategies)} стратегий")

    # Группировка по категориям
    by_group = {}
    for s in all_strategies:
        group = s['group']
        by_group[group] = by_group.get(group, 0) + 1

    print("\nПо группам:")
    for group, count in sorted(by_group.items()):
        print(f"  - {group}: {count} стратегий")

    # Сохранение в БД
    print("\nСохранение в базу данных...")
    db = Database()  # БД инициализируется автоматически в __init__

    inserted = 0
    for strategy in all_strategies:
        try:
            db.create_strategy(
                name=strategy['name'],
                type=strategy['type'],
                category=strategy['category'],
                symbol=strategy['symbol'],  # ✓ Добавлен symbol
                timeframe=strategy['timeframe'],
                direction=strategy['direction'],
                leverage=strategy['leverage'],
                params=strategy['params'],
                status=strategy['status']
            )
            inserted += 1
        except Exception as e:
            # Стратегия уже существует
            if "UNIQUE constraint" in str(e):
                continue
            print(f"Ошибка: {e}")

    print(f"[OK] Добавлено в БД: {inserted} стратегий")

    # Добавить 2 Live стратегии (4h Long + 15m Short)
    print("\nДобавление Live стратегий...")
    live_strategies = [
        {
            'name': 'live_4h_long',
            'type': 'supertrend',
            'category': 'live',
            'symbol': 'BTC/USDT:USDT',  # ✓ Добавлен symbol
            'timeframe': '4h',
            'direction': 'long',
            'leverage': 1,
            'params': json.dumps({'st_period': 10, 'st_multiplier': 3.0}),
            'status': 'stopped'
        },
        {
            'name': 'live_15m_short',
            'type': 'supertrend',
            'category': 'live',
            'symbol': 'BTC/USDT:USDT',  # ✓ Добавлен symbol
            'timeframe': '15m',
            'direction': 'short',
            'leverage': 1,
            'params': json.dumps({'st_period': 10, 'st_multiplier': 3.0}),
            'status': 'stopped'
        }
    ]

    for strategy in live_strategies:
        try:
            db.create_strategy(**strategy)
            print(f"[OK] {strategy['name']}")
        except Exception as e:
            if "UNIQUE constraint" not in str(e):
                print(f"Ошибка: {e}")

    # Подсчет реального количества в БД
    total_in_db = db.conn.execute("SELECT COUNT(*) FROM strategies").fetchone()[0]

    print("\n" + "=" * 60)
    print(f"Готово! Всего стратегий в БД: {total_in_db}")
    print("=" * 60)
    print("\nТеперь запустите платформу:")
    print("  python run_platform.py")
    print("\nИ откройте в браузере:")
    print("  http://localhost:5001")


if __name__ == "__main__":
    main()
