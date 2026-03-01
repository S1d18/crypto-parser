"""
Расширенная SQLite схема для 100+ стратегий.

Содержит:
- strategies: реестр всех стратегий
- trades: расширенная таблица сделок (strategy_id, leverage, pnl_percent)
- performance_metrics: метрики производительности по дням
- signals: история сигналов для screener
"""
import sqlite3
import logging
from pathlib import Path
from typing import Optional, List

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "data" / "platform.db"


class Database:
    """Единая база данных для всей платформы."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.conn = None
        self._connect()
        self._create_schema()

    def _connect(self):
        """Подключиться к БД."""
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        # Включить WAL mode для лучшей производительности
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        logger.info(f"База данных подключена: {self.db_path}")

    def _create_schema(self):
        """Создать схему БД."""

        # Таблица стратегий
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS strategies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                type TEXT NOT NULL,  -- 'supertrend', 'rsi', 'macd', 'arbitrage'
                category TEXT NOT NULL,  -- 'live', 'paper', 'arbitrage'
                symbol TEXT DEFAULT 'BTC/USDT:USDT',  -- Торговая пара
                timeframe TEXT,
                direction TEXT,  -- 'long', 'short', 'both'
                leverage INTEGER DEFAULT 1,  -- 1, 2, 5, 10
                params TEXT,  -- JSON с параметрами
                status TEXT DEFAULT 'stopped',  -- 'running', 'stopped', 'error'
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Расширенная таблица сделок
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,  -- 'buy', 'sell'
                direction TEXT NOT NULL,  -- 'long', 'short'
                qty REAL NOT NULL,
                leverage INTEGER DEFAULT 1,
                entry_price REAL NOT NULL,
                sl_price REAL,
                tp_price REAL,
                sl_order_id TEXT,
                opened_at TIMESTAMP NOT NULL,
                close_price REAL,
                closed_at TIMESTAMP,
                close_reason TEXT,  -- 'signal', 'sl_hit', 'tp_hit', 'manual'
                pnl REAL,
                pnl_percent REAL,
                fees REAL DEFAULT 0,
                status TEXT DEFAULT 'open',  -- 'open', 'closed'
                FOREIGN KEY (strategy_id) REFERENCES strategies(id)
            )
        """)

        # Индексы для trades
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_trades_strategy_status
            ON trades(strategy_id, status)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_trades_opened_at
            ON trades(opened_at DESC)
        """)

        # Метрики производительности (агрегаты по дням)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS performance_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_id INTEGER NOT NULL,
                date DATE NOT NULL,
                trades_count INTEGER DEFAULT 0,
                win_count INTEGER DEFAULT 0,
                loss_count INTEGER DEFAULT 0,
                total_pnl REAL DEFAULT 0,
                max_drawdown REAL DEFAULT 0,
                sharpe_ratio REAL,
                win_rate REAL,
                profit_factor REAL,
                expectancy REAL,
                avg_win REAL,
                avg_loss REAL,
                FOREIGN KEY (strategy_id) REFERENCES strategies(id),
                UNIQUE(strategy_id, date)
            )
        """)

        # Сигналы (для screener)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_id INTEGER NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                action TEXT NOT NULL,  -- 'buy', 'sell', 'close'
                price REAL NOT NULL,
                confidence REAL,  -- 0-100
                reason TEXT,
                executed BOOLEAN DEFAULT 0,
                FOREIGN KEY (strategy_id) REFERENCES strategies(id)
            )
        """)

        # Индекс для сигналов
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_signals_timestamp
            ON signals(timestamp DESC)
        """)

        # Миграция: добавить колонку symbol в strategies если её нет
        cursor = self.conn.execute("PRAGMA table_info(strategies)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'symbol' not in columns:
            logger.info("Миграция: добавление колонки symbol в strategies")
            self.conn.execute("ALTER TABLE strategies ADD COLUMN symbol TEXT DEFAULT 'BTC/USDT:USDT'")

        # Миграция: добавить колонку virtual_balance если её нет
        if 'virtual_balance' not in columns:
            logger.info("Миграция: добавление колонки virtual_balance в strategies")
            self.conn.execute("ALTER TABLE strategies ADD COLUMN virtual_balance REAL DEFAULT 1000.0")

        # Всегда синхронизировать symbol из названий стратегий
        # Формат: indicator_coin_timeframe_variant (например macd_btc_15m_fast)
        valid_coins = {'btc', 'eth', 'sol', 'ltc', 'ton'}
        strategies = self.conn.execute("SELECT id, name, symbol FROM strategies").fetchall()
        updated = 0
        for strategy_id, name, current_symbol in strategies:
            parts = name.split('_')
            coin = None

            # Если второй элемент - монета (btc, eth, sol, ltc, ton)
            if len(parts) >= 2 and parts[1].lower() in valid_coins:
                coin = parts[1].upper()

            if coin:
                correct_symbol = f"{coin}/USDT:USDT"
                if current_symbol != correct_symbol:
                    self.conn.execute("UPDATE strategies SET symbol = ? WHERE id = ?",
                                      (correct_symbol, strategy_id))
                    updated += 1

        if updated > 0:
            logger.info(f"Синхронизировано symbol для {updated} стратегий")

        self.conn.commit()
        logger.info("Схема БД создана/обновлена")

    def get_connection(self) -> sqlite3.Connection:
        """Получить connection для прямого использования."""
        return self.conn

    # =========================================================================
    # Методы для работы со стратегиями
    # =========================================================================

    def create_strategy(
        self,
        name: str,
        type: str,
        category: str,
        timeframe: str,
        direction: str,
        symbol: str = "BTC/USDT:USDT",  # ✓ Добавлен symbol
        leverage: int = 1,
        params: str = "{}",
        status: str = "stopped"
    ) -> int:
        """
        Создать новую стратегию.

        Args:
            name: уникальное имя стратегии
            type: тип ('supertrend', 'rsi', 'macd', и т.д.)
            category: категория ('live', 'paper', 'arbitrage')
            timeframe: таймфрейм ('1m', '5m', '1h', и т.д.)
            direction: направление ('long', 'short', 'both')
            symbol: торговая пара (по умолчанию BTC/USDT:USDT)
            leverage: кредитное плечо (1, 2, 5, 10)
            params: JSON с параметрами
            status: статус ('running', 'stopped', 'error')

        Returns:
            ID созданной стратегии
        """
        cursor = self.conn.execute("""
            INSERT INTO strategies (name, type, category, symbol, timeframe, direction, leverage, params, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (name, type, category, symbol, timeframe, direction, leverage, params, status))

        self.conn.commit()
        return cursor.lastrowid

    def get_strategy(self, strategy_id: int) -> Optional[dict]:
        """Получить стратегию по ID."""
        cursor = self.conn.execute("""
            SELECT * FROM strategies WHERE id = ?
        """, (strategy_id,))

        row = cursor.fetchone()
        return dict(row) if row else None

    def get_all_strategies(self) -> List[dict]:
        """Получить все стратегии."""
        cursor = self.conn.execute("SELECT * FROM strategies ORDER BY category, timeframe")
        return [dict(row) for row in cursor.fetchall()]

    def get_strategies_by_status(self, status: str) -> List[dict]:
        """Получить стратегии по статусу."""
        cursor = self.conn.execute("""
            SELECT * FROM strategies WHERE status = ?
        """, (status,))
        return [dict(row) for row in cursor.fetchall()]

    def get_strategies_by_category(self, category: str) -> List[dict]:
        """Получить стратегии по категории."""
        cursor = self.conn.execute("""
            SELECT * FROM strategies WHERE category = ?
        """, (category,))
        return [dict(row) for row in cursor.fetchall()]

    def update_strategy_status(self, strategy_id: int, status: str):
        """Обновить статус стратегии."""
        self.conn.execute("""
            UPDATE strategies SET status = ? WHERE id = ?
        """, (status, strategy_id))
        self.conn.commit()

    def delete_strategy(self, strategy_id: int):
        """Удалить стратегию."""
        self.conn.execute("DELETE FROM strategies WHERE id = ?", (strategy_id,))
        self.conn.commit()

    def close(self):
        """Закрыть соединение."""
        if self.conn:
            self.conn.close()
            logger.info("База данных закрыта")


# Singleton instance
_db_instance: Optional[Database] = None


def get_database() -> Database:
    """Получить singleton instance базы данных."""
    global _db_instance
    if _db_instance is None:
        _db_instance = Database()
    return _db_instance
