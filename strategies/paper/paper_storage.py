import sqlite3
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# Путь к БД относительно корня проекта
PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "paper_trades.db"


class PaperTradeStorage:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()
        logger.info(f"PaperTradeStorage инициализирован: {db_path}")

    def _create_tables(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS paper_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_id TEXT NOT NULL,
                strategy_group TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                direction INTEGER NOT NULL,
                qty REAL NOT NULL,
                entry_price REAL NOT NULL,
                sl_price REAL,
                opened_at TEXT NOT NULL,
                close_price REAL,
                closed_at TEXT,
                close_reason TEXT,
                pnl REAL,
                pnl_pct REAL,
                status TEXT NOT NULL DEFAULT 'open'
            )
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_paper_trades_strategy
            ON paper_trades(strategy_id, status)
        """)
        self.conn.commit()

    def save_open_trade(self, strategy_id: str, strategy_group: str,
                        timeframe: str, symbol: str, side: str,
                        direction: int, qty: float, entry_price: float,
                        sl_price: float = None) -> int:
        now = datetime.now(timezone.utc).isoformat()
        cursor = self.conn.execute("""
            INSERT INTO paper_trades
                (strategy_id, strategy_group, timeframe, symbol, side,
                 direction, qty, entry_price, sl_price, opened_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open')
        """, (strategy_id, strategy_group, timeframe, symbol, side,
              direction, qty, entry_price, sl_price, now))
        self.conn.commit()
        trade_id = cursor.lastrowid
        logger.info(f"[Paper] Сохранена сделка #{trade_id}: {strategy_id} {side} @ {entry_price}")
        return trade_id

    def close_trade(self, strategy_id: str, close_price: float,
                    reason: str, pnl: float, pnl_pct: float) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        cursor = self.conn.execute("""
            UPDATE paper_trades
            SET close_price = ?, closed_at = ?, close_reason = ?,
                pnl = ?, pnl_pct = ?, status = 'closed'
            WHERE strategy_id = ? AND status = 'open'
        """, (close_price, now, reason, pnl, pnl_pct, strategy_id))
        self.conn.commit()
        if cursor.rowcount > 0:
            logger.info(f"[Paper] Закрыта сделка {strategy_id}: {reason} @ {close_price}, PnL={pnl:+.2f} ({pnl_pct:+.2f}%)")
            return True
        logger.warning(f"[Paper] Не найдена открытая сделка для {strategy_id}")
        return False

    def get_open_trades(self, strategy_id: str = None) -> list[dict]:
        if strategy_id:
            rows = self.conn.execute(
                "SELECT * FROM paper_trades WHERE status = 'open' AND strategy_id = ?",
                (strategy_id,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM paper_trades WHERE status = 'open'"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_trade_history(self, strategy_id: str = None, group: str = None,
                          limit: int = 200, offset: int = 0) -> list[dict]:
        query = "SELECT * FROM paper_trades WHERE status = 'closed'"
        params = []
        if strategy_id:
            query += " AND strategy_id = ?"
            params.append(strategy_id)
        if group:
            query += " AND strategy_group = ?"
            params.append(group)
        query += " ORDER BY closed_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = self.conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def get_strategy_stats(self, strategy_id: str) -> dict:
        """Полная статистика по стратегии (TradingView-стиль)."""
        trades = self.conn.execute(
            "SELECT * FROM paper_trades WHERE status = 'closed' AND strategy_id = ? ORDER BY closed_at",
            (strategy_id,),
        ).fetchall()
        trades = [dict(r) for r in trades]

        open_trade = self.conn.execute(
            "SELECT * FROM paper_trades WHERE status = 'open' AND strategy_id = ? LIMIT 1",
            (strategy_id,),
        ).fetchone()

        if not trades:
            return {
                "total": 0, "wins": 0, "losses": 0,
                "win_rate": 0.0, "total_pnl": 0.0, "total_pnl_pct": 0.0,
                "avg_pnl": 0.0, "avg_win": 0.0, "avg_loss": 0.0,
                "profit_factor": 0.0, "max_drawdown": 0.0,
                "sharpe": 0.0, "expectancy": 0.0,
                "max_consec_wins": 0, "max_consec_losses": 0,
                "sl_hits": 0, "has_open_position": open_trade is not None,
                "open_trade": dict(open_trade) if open_trade else None,
            }

        pnls = [t["pnl"] for t in trades]
        pnl_pcts = [t["pnl_pct"] for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        sl_hits = sum(1 for t in trades if t["close_reason"] == "sl_hit")

        gross_profit = sum(wins) if wins else 0.0
        gross_loss = abs(sum(losses)) if losses else 0.0

        # Max Drawdown
        equity_curve = []
        running = 0.0
        for p in pnls:
            running += p
            equity_curve.append(running)
        peak = 0.0
        max_dd = 0.0
        for eq in equity_curve:
            if eq > peak:
                peak = eq
            dd = peak - eq
            if dd > max_dd:
                max_dd = dd

        # Sharpe (упрощённый — mean/std по pnl_pct)
        import statistics
        sharpe = 0.0
        if len(pnl_pcts) > 1:
            mean_r = statistics.mean(pnl_pcts)
            std_r = statistics.stdev(pnl_pcts)
            if std_r > 0:
                sharpe = round(mean_r / std_r, 2)

        # Consecutive wins/losses
        max_cw = max_cl = cw = cl = 0
        for p in pnls:
            if p > 0:
                cw += 1
                cl = 0
            else:
                cl += 1
                cw = 0
            max_cw = max(max_cw, cw)
            max_cl = max(max_cl, cl)

        # Expectancy = avg_win * win_rate - avg_loss * loss_rate
        wr = len(wins) / len(trades) if trades else 0
        lr = len(losses) / len(trades) if trades else 0
        avg_w = gross_profit / len(wins) if wins else 0
        avg_l = gross_loss / len(losses) if losses else 0
        expectancy = avg_w * wr - avg_l * lr

        return {
            "total": len(trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(wr * 100, 1),
            "total_pnl": round(sum(pnls), 2),
            "total_pnl_pct": round(sum(pnl_pcts), 2),
            "avg_pnl": round(sum(pnls) / len(trades), 2),
            "avg_win": round(avg_w, 2),
            "avg_loss": round(-avg_l, 2),
            "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss > 0 else float("inf"),
            "max_drawdown": round(max_dd, 2),
            "sharpe": sharpe,
            "expectancy": round(expectancy, 2),
            "max_consec_wins": max_cw,
            "max_consec_losses": max_cl,
            "sl_hits": sl_hits,
            "has_open_position": open_trade is not None,
            "open_trade": dict(open_trade) if open_trade else None,
        }

    def get_all_strategies_summary(self) -> list[dict]:
        """Сводка для главной страницы — по всем strategy_id."""
        rows = self.conn.execute("""
            SELECT
                strategy_id,
                strategy_group,
                timeframe,
                COUNT(*) as total_trades,
                SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN pnl <= 0 THEN 1 ELSE 0 END) as losses,
                ROUND(SUM(pnl), 2) as total_pnl,
                ROUND(SUM(pnl_pct), 2) as total_pnl_pct,
                ROUND(
                    CASE WHEN SUM(CASE WHEN pnl <= 0 THEN ABS(pnl) ELSE 0 END) > 0
                    THEN SUM(CASE WHEN pnl > 0 THEN pnl ELSE 0 END) /
                         SUM(CASE WHEN pnl <= 0 THEN ABS(pnl) ELSE 0 END)
                    ELSE 0 END, 2
                ) as profit_factor
            FROM paper_trades
            WHERE status = 'closed'
            GROUP BY strategy_id
        """).fetchall()
        return [dict(r) for r in rows]

    def get_equity_curve(self, strategy_id: str) -> list[dict]:
        """Кривая эквити для графика."""
        trades = self.conn.execute(
            "SELECT closed_at, pnl FROM paper_trades WHERE status = 'closed' AND strategy_id = ? ORDER BY closed_at",
            (strategy_id,),
        ).fetchall()
        curve = []
        running = 0.0
        for t in trades:
            running += t["pnl"]
            curve.append({"time": t["closed_at"], "value": round(running, 2)})
        return curve

    def close(self):
        self.conn.close()
