"""Flask веб-интерфейс для торгового бота Supertrend."""

from flask import Flask, render_template, jsonify, request
from datetime import datetime, timedelta
import sys
from pathlib import Path

# Добавляем корневую директорию в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

from storage import TradeStorage
from config import Config


def create_app():
    """Создание Flask приложения."""
    app = Flask(__name__,
                template_folder="templates",
                static_folder="static")

    config = Config()

    def get_storage():
        """Создать новое подключение к БД для каждого запроса."""
        return TradeStorage()

    @app.route("/")
    def dashboard():
        """Главная страница дашборда."""
        return render_template("dashboard.html")

    @app.route("/api/status")
    def get_status():
        """API: статус бота и текущие позиции."""
        # Получаем открытые позиции
        storage = get_storage()
        open_trades = storage.get_open_trades()

        # Формируем данные по позициям
        positions = []
        for trade in open_trades:
            positions.append({
                "timeframe": trade["timeframe"],
                "symbol": trade["symbol"],
                "direction": trade["direction"],
                "side": trade["side"],
                "entry_price": float(trade["entry_price"]),
                "quantity": float(trade["qty"]),
                "sl_price": float(trade["sl_price"]),
                "opened_at": trade["opened_at"],
                "pnl": 0.0,
                "pnl_pct": 0.0
            })

        return jsonify({
            "bot_running": True,
            "last_update": datetime.now().isoformat(),
            "positions": positions,
            "symbol": config.symbol
        })

    @app.route("/api/statistics")
    def get_statistics():
        """API: статистика по сделкам."""
        storage = get_storage()
        all_trades = storage.get_all_trades()
        closed_trades = [t for t in all_trades if t["status"] == "closed"]

        if not closed_trades:
            return jsonify({
                "total_trades": 0,
                "profitable_trades": 0,
                "losing_trades": 0,
                "win_rate": 0.0,
                "total_pnl": 0.0,
                "avg_profit": 0.0,
                "avg_loss": 0.0,
                "avg_trade": 0.0,
                "best_trade": 0.0,
                "worst_trade": 0.0
            })

        # Рассчитываем статистику
        profitable = [t for t in closed_trades if t["pnl"] and float(t["pnl"]) > 0]
        losing = [t for t in closed_trades if t["pnl"] and float(t["pnl"]) < 0]

        total_pnl = sum(float(t["pnl"]) for t in closed_trades if t["pnl"])

        return jsonify({
            "total_trades": len(closed_trades),
            "profitable_trades": len(profitable),
            "losing_trades": len(losing),
            "win_rate": (len(profitable) / len(closed_trades) * 100) if closed_trades else 0,
            "total_pnl": total_pnl,
            "avg_profit": sum(float(t["pnl"]) for t in profitable) / len(profitable) if profitable else 0,
            "avg_loss": sum(float(t["pnl"]) for t in losing) / len(losing) if losing else 0,
            "avg_trade": total_pnl / len(closed_trades) if closed_trades else 0,
            "best_trade": max((float(t["pnl"]) for t in closed_trades if t["pnl"]), default=0),
            "worst_trade": min((float(t["pnl"]) for t in closed_trades if t["pnl"]), default=0)
        })

    @app.route("/api/trades")
    def get_trades():
        """API: история сделок."""
        limit = request.args.get("limit", 50, type=int)
        timeframe = request.args.get("timeframe", None)

        storage = get_storage()
        all_trades = storage.get_all_trades()

        if timeframe:
            all_trades = [t for t in all_trades if t["timeframe"] == timeframe]

        all_trades.sort(key=lambda x: x["opened_at"], reverse=True)
        trades = all_trades[:limit]

        result = []
        for trade in trades:
            result.append({
                "id": trade["id"],
                "timeframe": trade["timeframe"],
                "symbol": trade["symbol"],
                "direction": trade["direction"],
                "side": trade["side"],
                "entry_price": float(trade["entry_price"]),
                "close_price": float(trade["close_price"]) if trade["close_price"] else None,
                "quantity": float(trade["qty"]),
                "sl_price": float(trade["sl_price"]),
                "opened_at": trade["opened_at"],
                "closed_at": trade["closed_at"],
                "close_reason": trade["close_reason"],
                "pnl": float(trade["pnl"]) if trade["pnl"] else 0.0,
                "status": trade["status"]
            })

        return jsonify(result)

    @app.route("/api/chart-data")
    def get_chart_data():
        """API: данные для графика баланса."""
        days = request.args.get("days", 30, type=int)

        storage = get_storage()
        all_trades = storage.get_all_trades()
        closed_trades = [t for t in all_trades if t["status"] == "closed" and t["closed_at"]]

        closed_trades.sort(key=lambda x: x["closed_at"])

        cumulative_pnl = []
        total = 0.0

        for trade in closed_trades:
            if trade["pnl"]:
                total += float(trade["pnl"])
                cumulative_pnl.append({
                    "timestamp": trade["closed_at"],
                    "pnl": round(total, 2)
                })

        cutoff_date = datetime.now() - timedelta(days=days)
        cumulative_pnl = [
            p for p in cumulative_pnl
            if datetime.fromisoformat(p["timestamp"]) >= cutoff_date
        ]

        return jsonify(cumulative_pnl)

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5001, debug=True)
