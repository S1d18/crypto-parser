"""Сброс всех Supertrend стратегий - удаление сделок и сброс балансов."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.database import Database

db = Database()

# 1. Статистика до очистки
st_ids = db.conn.execute("SELECT id, name FROM strategies WHERE type='supertrend'").fetchall()
print(f"Supertrend стратегий: {len(st_ids)}")

trade_count = db.conn.execute(
    "SELECT COUNT(*) FROM trades WHERE strategy_id IN (SELECT id FROM strategies WHERE type='supertrend')"
).fetchone()[0]
print(f"Сделок (удаляем): {trade_count}")

open_count = db.conn.execute(
    "SELECT COUNT(*) FROM trades WHERE strategy_id IN (SELECT id FROM strategies WHERE type='supertrend') AND status='open'"
).fetchone()[0]
print(f"Открытых позиций: {open_count}")

pnl = db.conn.execute(
    "SELECT COALESCE(SUM(pnl), 0) FROM trades WHERE strategy_id IN (SELECT id FROM strategies WHERE type='supertrend') AND status='closed'"
).fetchone()[0]
print(f"Общий PnL (теряем): ${pnl:.2f}")

print("\n--- Очистка ---")

# 2. Удалить все сделки Supertrend
db.conn.execute(
    "DELETE FROM trades WHERE strategy_id IN (SELECT id FROM strategies WHERE type='supertrend')"
)
print(f"[OK] Удалено {trade_count} сделок")

# 3. Сбросить балансы на 1000
db.conn.execute(
    "UPDATE strategies SET virtual_balance = 1000.0 WHERE type='supertrend'"
)
print(f"[OK] Сброшены балансы на $1000 для {len(st_ids)} стратегий")

db.conn.commit()

# 4. Проверка
remaining = db.conn.execute(
    "SELECT COUNT(*) FROM trades WHERE strategy_id IN (SELECT id FROM strategies WHERE type='supertrend')"
).fetchone()[0]
print(f"\nОсталось сделок Supertrend: {remaining}")

total_trades = db.conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
print(f"Всего сделок в БД (RSI+MACD): {total_trades}")

print("\n[OK] Supertrend стратегии очищены! Перезапустите сервис.")
