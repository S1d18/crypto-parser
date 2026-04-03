import sqlite3
import os
from datetime import datetime, date


class Storage:
    def __init__(self, db_path: str = "data/scalper.db"):
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        cur = self.conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                direction TEXT NOT NULL,
                qty REAL NOT NULL,
                leverage INTEGER NOT NULL,
                margin REAL NOT NULL,
                entry_price REAL NOT NULL,
                sl_price REAL NOT NULL,
                tp_price REAL NOT NULL,
                exit_price REAL,
                pnl REAL,
                pnl_pct REAL,
                reasons TEXT,
                close_reason TEXT,
                opened_at TEXT NOT NULL,
                closed_at TEXT,
                status TEXT NOT NULL DEFAULT 'open'
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS equity_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                balance REAL NOT NULL,
                timestamp TEXT NOT NULL
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        self.conn.commit()

    def open_trade(self, symbol: str, direction: str, qty: float,
                   entry_price: float, sl_price: float, tp_price: float,
                   leverage: int, margin: float, reasons: str = "") -> int:
        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO trades (symbol, direction, qty, leverage, margin,
                                entry_price, sl_price, tp_price, reasons, opened_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open')
        """, (symbol, direction, qty, leverage, margin,
              entry_price, sl_price, tp_price, reasons, datetime.now().isoformat()))
        self.conn.commit()
        return cur.lastrowid

    def close_trade(self, trade_id: int, exit_price: float, pnl: float,
                    pnl_pct: float, close_reason: str):
        cur = self.conn.cursor()
        cur.execute("""
            UPDATE trades
            SET exit_price = ?, pnl = ?, pnl_pct = ?, close_reason = ?,
                closed_at = ?, status = 'closed'
            WHERE id = ?
        """, (exit_price, pnl, pnl_pct, close_reason, datetime.now().isoformat(), trade_id))
        self.conn.commit()

    def get_open_trades(self) -> list[dict]:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM trades WHERE status = 'open'")
        return [dict(row) for row in cur.fetchall()]

    def get_daily_stats(self, day=None) -> dict:
        if day is None:
            day = date.today().isoformat()
        cur = self.conn.cursor()
        cur.execute("""
            SELECT * FROM trades
            WHERE status = 'closed' AND closed_at LIKE ?
        """, (f"{day}%",))
        rows = cur.fetchall()
        return self._calc_stats(rows)

    def get_all_stats(self) -> dict:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM trades WHERE status = 'closed'")
        rows = cur.fetchall()
        return self._calc_stats(rows)

    def _calc_stats(self, rows) -> dict:
        total = len(rows)
        total_pnl = sum(r["pnl"] for r in rows)
        wins = sum(1 for r in rows if r["pnl"] > 0)
        losses = total - wins
        win_rate = (wins / total * 100) if total > 0 else 0.0
        return {
            "total_trades": total,
            "total_pnl": total_pnl,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
        }

    def get_trade_history(self, limit: int = 50) -> list[dict]:
        cur = self.conn.cursor()
        cur.execute("""
            SELECT * FROM trades
            WHERE status = 'closed'
            ORDER BY closed_at DESC
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cur.fetchall()]

    def save_equity_snapshot(self, balance: float):
        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO equity_history (balance, timestamp)
            VALUES (?, ?)
        """, (balance, datetime.now().isoformat()))
        self.conn.commit()

    def get_equity_history(self) -> list[dict]:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM equity_history ORDER BY id ASC")
        return [dict(row) for row in cur.fetchall()]

    def save_state(self, key: str, value: str):
        self.conn.execute(
            "INSERT OR REPLACE INTO state (key, value) VALUES (?, ?)",
            (key, value))
        self.conn.commit()

    def get_state(self, key: str, default: str = None) -> str | None:
        row = self.conn.execute(
            "SELECT value FROM state WHERE key = ?", (key,)
        ).fetchone()
        return row['value'] if row else default

    def close(self):
        self.conn.close()
