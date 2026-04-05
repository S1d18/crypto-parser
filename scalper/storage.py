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
                confidence INTEGER DEFAULT 60,
                peak_pnl REAL DEFAULT 0,
                peak_price REAL,
                missed_pnl REAL DEFAULT 0,
                time_held_sec INTEGER DEFAULT 0,
                opened_at TEXT NOT NULL,
                closed_at TEXT,
                status TEXT NOT NULL DEFAULT 'open'
            )
        """)
        # Add columns to existing DBs (safe — ignores if exists)
        for col, typ in [('confidence', 'INTEGER DEFAULT 60'),
                         ('peak_pnl', 'REAL DEFAULT 0'),
                         ('peak_price', 'REAL'),
                         ('missed_pnl', 'REAL DEFAULT 0'),
                         ('time_held_sec', 'INTEGER DEFAULT 0')]:
            try:
                cur.execute(f"ALTER TABLE trades ADD COLUMN {col} {typ}")
            except sqlite3.OperationalError:
                pass
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
        cur.execute("""
            CREATE TABLE IF NOT EXISTS trade_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                price REAL,
                details TEXT,
                timestamp TEXT NOT NULL
            )
        """)
        self.conn.commit()

    def open_trade(self, symbol: str, direction: str, qty: float,
                   entry_price: float, sl_price: float, tp_price: float,
                   leverage: int, margin: float, reasons: str = "",
                   confidence: int = 60) -> int:
        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO trades (symbol, direction, qty, leverage, margin,
                                entry_price, sl_price, tp_price, reasons, confidence,
                                opened_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open')
        """, (symbol, direction, qty, leverage, margin,
              entry_price, sl_price, tp_price, reasons, confidence,
              datetime.now().isoformat()))
        self.conn.commit()
        return cur.lastrowid

    def close_trade(self, trade_id: int, exit_price: float, pnl: float,
                    pnl_pct: float, close_reason: str,
                    peak_pnl: float = 0, peak_price: float = None,
                    time_held_sec: int = 0):
        missed_pnl = round(peak_pnl - pnl, 4) if peak_pnl > pnl else 0
        cur = self.conn.cursor()
        cur.execute("""
            UPDATE trades
            SET exit_price = ?, pnl = ?, pnl_pct = ?, close_reason = ?,
                peak_pnl = ?, peak_price = ?, missed_pnl = ?,
                time_held_sec = ?, closed_at = ?, status = 'closed'
            WHERE id = ?
        """, (exit_price, pnl, pnl_pct, close_reason,
              peak_pnl, peak_price, missed_pnl,
              time_held_sec, datetime.now().isoformat(), trade_id))
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
        avg_pnl = (total_pnl / total) if total > 0 else 0.0

        win_pnls = [r["pnl"] for r in rows if r["pnl"] > 0]
        loss_pnls = [r["pnl"] for r in rows if r["pnl"] <= 0]
        avg_win = (sum(win_pnls) / len(win_pnls)) if win_pnls else 0.0
        avg_loss = (sum(loss_pnls) / len(loss_pnls)) if loss_pnls else 0.0
        profit_factor = (sum(win_pnls) / abs(sum(loss_pnls))) if loss_pnls and sum(loss_pnls) != 0 else 0.0
        best_trade = max((r["pnl"] for r in rows), default=0.0)
        worst_trade = min((r["pnl"] for r in rows), default=0.0)

        # Missed profit analysis
        missed_pnls = []
        times = []
        for r in rows:
            try:
                mp = r["missed_pnl"]
                if mp and mp > 0:
                    missed_pnls.append(mp)
            except (IndexError, KeyError):
                pass
            try:
                th = r["time_held_sec"]
                if th and th > 0:
                    times.append(th)
            except (IndexError, KeyError):
                pass
        total_missed = sum(missed_pnls) if missed_pnls else 0
        avg_missed = (total_missed / len(missed_pnls)) if missed_pnls else 0
        avg_time = (sum(times) / len(times)) if times else 0

        return {
            "total_trades": total,
            "total_pnl": round(total_pnl, 2),
            "wins": wins,
            "losses": losses,
            "win_rate": round(win_rate, 1),
            "avg_pnl": round(avg_pnl, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "profit_factor": round(profit_factor, 2),
            "best_trade": round(best_trade, 2),
            "worst_trade": round(worst_trade, 2),
            "total_missed_pnl": round(total_missed, 2),
            "avg_missed_pnl": round(avg_missed, 2),
            "avg_time_min": round(avg_time / 60, 1),
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

    def add_trade_event(self, trade_id: int, event_type: str,
                        price: float = None, details: str = ''):
        self.conn.execute(
            "INSERT INTO trade_events (trade_id, event_type, price, details, timestamp) VALUES (?, ?, ?, ?, ?)",
            (trade_id, event_type, price, details, datetime.now().isoformat()))
        self.conn.commit()

    def get_trade_events(self, trade_id: int) -> list[dict]:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT * FROM trade_events WHERE trade_id = ? ORDER BY id ASC",
            (trade_id,))
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
