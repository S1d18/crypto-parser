"""
Миграция: создать варианты стратегий с разными SL%.

Для каждой из 1352 стратегий создаём копии с каждым SL% из таблицы,
кроме того SL%, который уже стоит (по таймфрейму).

Пример: supertrend_btc_4h_std_long (SL=3.0%) →
  supertrend_btc_4h_std_long_sl0.3  (SL=0.3%)
  supertrend_btc_4h_std_long_sl0.5  (SL=0.5%)
  supertrend_btc_4h_std_long_sl0.75 (SL=0.75%)
  ... и т.д. (все кроме 3.0%)

Итого: ~13,520 новых стратегий.
"""

import sys
from pathlib import Path
import json

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.database import Database

# Все значения SL% для тестирования
SL_VALUES = [0.3, 0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0]


def main():
    print("=" * 60)
    print("Создание вариантов стратегий с разными SL%")
    print(f"SL% значения: {SL_VALUES}")
    print("=" * 60)

    db = Database()

    # Получить все существующие стратегии
    strategies = db.conn.execute(
        "SELECT id, name, type, category, symbol, timeframe, direction, leverage, params, status FROM strategies"
    ).fetchall()

    print(f"Существующих стратегий: {len(strategies)}")

    inserted = 0
    skipped = 0
    errors = 0

    for s in strategies:
        try:
            params = json.loads(s['params']) if s['params'] else {}
        except (json.JSONDecodeError, TypeError):
            params = {}

        current_sl = params.get('sl_percent')

        for sl_val in SL_VALUES:
            # Пропустить текущее значение SL%
            if current_sl is not None and abs(sl_val - current_sl) < 0.001:
                continue

            # Новое имя с суффиксом SL
            sl_suffix = f"_sl{sl_val}"
            new_name = s['name'] + sl_suffix

            # Новые params с другим SL%
            new_params = dict(params)
            new_params['sl_percent'] = sl_val

            try:
                db.create_strategy(
                    name=new_name,
                    type=s['type'],
                    category=s['category'],
                    symbol=s['symbol'],
                    timeframe=s['timeframe'],
                    direction=s['direction'],
                    leverage=s['leverage'],
                    params=json.dumps(new_params),
                    status='stopped',
                )
                inserted += 1
            except Exception as e:
                if "UNIQUE constraint" in str(e):
                    skipped += 1
                else:
                    errors += 1
                    if errors <= 5:
                        print(f"  ERROR: {new_name}: {e}")

        # Прогресс
        if (strategies.index(s) + 1) % 200 == 0:
            print(f"  Обработано {strategies.index(s) + 1}/{len(strategies)}... (добавлено: {inserted})")

    db.conn.commit()

    total = db.conn.execute("SELECT COUNT(*) FROM strategies").fetchone()[0]

    print(f"\nДобавлено: {inserted}")
    print(f"Уже существовали: {skipped}")
    print(f"Ошибок: {errors}")
    print(f"Всего стратегий в БД: {total}")

    # Примеры
    sample = db.conn.execute("""
        SELECT name, timeframe, params FROM strategies
        WHERE name LIKE '%_sl%'
        ORDER BY name LIMIT 15
    """).fetchall()

    print(f"\nПримеры новых стратегий:")
    for s in sample:
        p = json.loads(s['params'])
        print(f"  {s['name']:55s} TF={s['timeframe']:4s} SL={p.get('sl_percent')}%")

    # Распределение
    print(f"\nРаспределение по SL%:")
    for sl in SL_VALUES:
        count = db.conn.execute(
            "SELECT COUNT(*) FROM strategies WHERE params LIKE ?",
            (f'%"sl_percent": {sl}%',)
        ).fetchone()[0]
        # Для дробных значений проверим оба формата
        if count == 0:
            count = db.conn.execute(
                "SELECT COUNT(*) FROM strategies WHERE params LIKE ?",
                (f'%"sl_percent": {sl:.1f}%',)
            ).fetchone()[0]
        print(f"  SL={sl}%: {count} стратегий")

    print("=" * 60)


if __name__ == "__main__":
    main()
