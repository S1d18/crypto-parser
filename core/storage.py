import sqlite3
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# Путь к БД относительно корня проекта
PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "data" / "trades.db"


class TradeStorage:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()
        logger.info(f"TradeStorage инициализирован: {db_path}")

    def _create_tables(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timeframe TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                direction INTEGER NOT NULL,
                qty REAL NOT NULL,
                entry_price REAL NOT NULL,
                sl_price REAL,
                sl_order_id TEXT,
                opened_at TEXT NOT NULL,
                close_price REAL,
                closed_at TEXT,
                close_reason TEXT,
                pnl REAL,
                status TEXT NOT NULL DEFAULT 'open'
            )
        """)
        self.conn.commit()

    def save_open_trade(self, timeframe: str, symbol: str, side: str,
                        direction: int, qty: float, entry_price: float,
                        sl_price: float = None, sl_order_id: str = None) -> int:
        now = datetime.now(timezone.utc).isoformat()
        cursor = self.conn.execute("""
            INSERT INTO trades (timeframe, symbol, side, direction, qty,
                                entry_price, sl_price, sl_order_id, opened_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open')
        """, (timeframe, symbol, side, direction, qty,
              entry_price, sl_price, sl_order_id, now))
        self.conn.commit()
        trade_id = cursor.lastrowid
        logger.info(f"[DB] Сохранена сделка #{trade_id}: {side} {timeframe} @ {entry_price}")
        return trade_id

    def close_trade(self, timeframe: str, close_price: float,
                    reason: str, pnl: float) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        cursor = self.conn.execute("""
            UPDATE trades
            SET close_price = ?, closed_at = ?, close_reason = ?, pnl = ?, status = 'closed'
            WHERE timeframe = ? AND status = 'open'
        """, (close_price, now, reason, pnl, timeframe))
        self.conn.commit()
        if cursor.rowcount > 0:
            logger.info(f"[DB] Закрыта сделка {timeframe}: {reason} @ {close_price}, PnL={pnl:+.2f}")
            return True
        logger.warning(f"[DB] Не найдена открытая сделка для {timeframe}")
        return False

    def get_open_trades(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM trades WHERE status = 'open'"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_all_trades(self) -> list[dict]:
        """Получить все сделки (открытые и закрытые)."""
        rows = self.conn.execute(
            "SELECT * FROM trades ORDER BY opened_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_trade_history(self, timeframe: str = None, limit: int = 100) -> list[dict]:
        if timeframe:
            rows = self.conn.execute(
                "SELECT * FROM trades WHERE status = 'closed' AND timeframe = ? "
                "ORDER BY closed_at DESC LIMIT ?",
                (timeframe, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM trades WHERE status = 'closed' "
                "ORDER BY closed_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_statistics(self, timeframe: str = None) -> dict:
        if timeframe:
            trades = self.conn.execute(
                "SELECT pnl, close_reason FROM trades WHERE status = 'closed' AND timeframe = ?",
                (timeframe,),
            ).fetchall()
        else:
            trades = self.conn.execute(
                "SELECT pnl, close_reason FROM trades WHERE status = 'closed'"
            ).fetchall()

        if not trades:
            return {
                "total": 0, "wins": 0, "losses": 0,
                "win_rate": 0.0, "total_pnl": 0.0,
                "avg_pnl": 0.0, "avg_win": 0.0, "avg_loss": 0.0,
                "profit_factor": 0.0, "sl_hits": 0,
            }

        pnls = [t["pnl"] for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        sl_hits = sum(1 for t in trades if t["close_reason"] == "sl_hit")

        gross_profit = sum(wins) if wins else 0.0
        gross_loss = abs(sum(losses)) if losses else 0.0

        return {
            "total": len(trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": len(wins) / len(trades) * 100 if trades else 0.0,
            "total_pnl": sum(pnls),
            "avg_pnl": sum(pnls) / len(trades) if trades else 0.0,
            "avg_win": gross_profit / len(wins) if wins else 0.0,
            "avg_loss": -gross_loss / len(losses) if losses else 0.0,
            "profit_factor": gross_profit / gross_loss if gross_loss > 0 else float("inf"),
            "sl_hits": sl_hits,
        }

    def close(self):
        self.conn.close()
