"""
Миграция: добавить sl_percent в params каждой стратегии.

SL% зависит от таймфрейма (базовый), но хранится индивидуально
в params каждой стратегии — можно менять под конкретную стратегию.
"""

import sys
from pathlib import Path
import json

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.database import Database

# Базовые SL% по таймфрейму
SL_BY_TF = {
    '1m': 0.3,  '3m': 0.5,  '5m': 0.75,
    '15m': 1.0, '30m': 1.5,
    '1h': 2.0,  '2h': 2.5,
    '4h': 3.0,  '6h': 3.5,
    '12h': 4.0, '1d': 5.0,
}


def main():
    print("=" * 60)
    print("Миграция: добавить sl_percent в params стратегий")
    print("=" * 60)

    db = Database()

    strategies = db.conn.execute(
        "SELECT id, name, timeframe, params FROM strategies"
    ).fetchall()

    updated = 0
    already = 0

    for s in strategies:
        try:
            params = json.loads(s['params']) if s['params'] else {}
        except (json.JSONDecodeError, TypeError):
            params = {}

        # Уже есть sl_percent — пропустить
        if 'sl_percent' in params:
            already += 1
            continue

        # Назначить SL% по таймфрейму
        tf = s['timeframe']
        sl = SL_BY_TF.get(tf, 2.0)

        params['sl_percent'] = sl

        db.conn.execute(
            "UPDATE strategies SET params = ? WHERE id = ?",
            (json.dumps(params), s['id'])
        )
        updated += 1

    db.conn.commit()

    # Проверка
    sample = db.conn.execute("""
        SELECT name, timeframe, params FROM strategies
        ORDER BY timeframe, name LIMIT 20
    """).fetchall()

    print(f"\nОбновлено: {updated}")
    print(f"Уже имели sl_percent: {already}")

    print(f"\nПримеры:")
    for s in sample:
        p = json.loads(s['params'])
        print(f"  {s['name']:45s} TF={s['timeframe']:4s} SL={p.get('sl_percent')}%")

    # Статистика SL% распределения
    print(f"\nРаспределение SL% по таймфреймам:")
    for tf in sorted(SL_BY_TF.keys(), key=lambda x: list(SL_BY_TF.keys()).index(x)):
        count = db.conn.execute(
            "SELECT COUNT(*) FROM strategies WHERE timeframe = ?", (tf,)
        ).fetchone()[0]
        print(f"  {tf:4s}: SL={SL_BY_TF[tf]}%  ({count} стратегий)")

    total = db.conn.execute("SELECT COUNT(*) FROM strategies").fetchone()[0]
    print(f"\nВсего стратегий: {total}")
    print("=" * 60)


if __name__ == "__main__":
    main()
