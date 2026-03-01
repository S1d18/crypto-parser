"""
Инициализация виртуальных счетов для paper trading.

Для каждой стратегии создаётся виртуальный счёт:
- Начальный баланс: 1000 USDT
- Размер позиции: 10% (100 USDT)
- Stop Loss: 10%
"""
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.database import Database


def init_virtual_accounts():
    """Создать виртуальные счета для всех стратегий."""
    db = Database()

    # Добавить колонку virtual_balance если её нет
    try:
        db.conn.execute("ALTER TABLE strategies ADD COLUMN virtual_balance REAL DEFAULT 1000.0")
        db.conn.commit()
        print("[OK] Добавлена колонка virtual_balance")
    except sqlite3.OperationalError:
        print("[OK] Колонка virtual_balance уже существует")

    # Добавить колонку position_size_pct если её нет
    try:
        db.conn.execute("ALTER TABLE strategies ADD COLUMN position_size_pct REAL DEFAULT 10.0")
        db.conn.commit()
        print("[OK] Добавлена колонка position_size_pct")
    except sqlite3.OperationalError:
        print("[OK] Колонка position_size_pct уже существует")

    # Добавить колонку sl_percent если её нет
    try:
        db.conn.execute("ALTER TABLE strategies ADD COLUMN sl_percent REAL DEFAULT 10.0")
        db.conn.commit()
        print("[OK] Добавлена колонка sl_percent")
    except sqlite3.OperationalError:
        print("[OK] Колонка sl_percent уже существует")

    # Установить начальные балансы для всех стратегий
    db.conn.execute("""
        UPDATE strategies
        SET virtual_balance = 1000.0,
            position_size_pct = 10.0,
            sl_percent = 10.0
        WHERE virtual_balance IS NULL OR virtual_balance = 0
    """)
    db.conn.commit()

    # Получить статистику
    cursor = db.conn.execute("""
        SELECT
            COUNT(*) as total,
            SUM(virtual_balance) as total_balance
        FROM strategies
    """)

    row = cursor.fetchone()
    total = row[0]
    total_balance = row[1]

    print(f"\n{'='*60}")
    print(f"Виртуальные счета инициализированы:")
    print(f"  Стратегий: {total}")
    print(f"  Баланс каждой: 1000 USDT")
    print(f"  Размер позиции: 10% (100 USDT)")
    print(f"  Stop Loss: 10%")
    print(f"  Общий виртуальный капитал: {total_balance:,.2f} USDT")
    print(f"{'='*60}")


if __name__ == "__main__":
    init_virtual_accounts()
