"""
Dashboard: графики и статистика торгового бота.

Запуск:
    python dashboard.py [--timeframe 4h] [--last 50] [--save chart.png] [--no-chart]
"""
import argparse
import sys
from datetime import datetime

from core.storage import TradeStorage


def print_statistics(storage: TradeStorage, timeframe: str = None):
    stats = storage.get_statistics(timeframe)
    label = timeframe or "ALL"

    print(f"\n{'=' * 60}")
    print(f"  Статистика: {label}")
    print(f"{'=' * 60}")
    print(f"  Total trades:    {stats['total']}")
    print(f"  Wins / Losses:   {stats['wins']} / {stats['losses']}")
    print(f"  Win Rate:        {stats['win_rate']:.1f}%")
    print(f"  Total PnL:       {stats['total_pnl']:+,.2f} USDT")
    print(f"  Avg PnL:         {stats['avg_pnl']:+,.2f} USDT")
    print(f"  Avg Win:         {stats['avg_win']:+,.2f} USDT")
    print(f"  Avg Loss:        {stats['avg_loss']:+,.2f} USDT")
    pf = stats['profit_factor']
    pf_str = f"{pf:.2f}" if pf != float("inf") else "inf"
    print(f"  Profit Factor:   {pf_str}")
    print(f"  SL Hits:         {stats['sl_hits']}")
    print(f"{'=' * 60}")


def print_all_statistics(storage: TradeStorage):
    print_statistics(storage)

    # Получаем уникальные таймфреймы
    rows = storage.conn.execute(
        "SELECT DISTINCT timeframe FROM trades WHERE status = 'closed'"
    ).fetchall()
    timeframes = [r["timeframe"] for r in rows]

    for tf in sorted(timeframes):
        print_statistics(storage, tf)


def build_chart(storage: TradeStorage, timeframe: str = None,
                last: int = 50, save_path: str = None):
    try:
        import matplotlib
        matplotlib.use("Agg" if save_path else "TkAgg")
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
    except ImportError:
        print("matplotlib не установлен. Установите: pip install matplotlib")
        return

    trades = storage.get_trade_history(timeframe, limit=last)
    if not trades:
        print("Нет закрытых сделок для отображения.")
        return

    # Сортируем по дате закрытия (старые → новые)
    trades = sorted(trades, key=lambda t: t["closed_at"])

    # Данные для графика
    dates = []
    entry_prices = []
    close_prices = []
    sides = []
    pnls = []
    reasons = []

    for t in trades:
        opened = datetime.fromisoformat(t["opened_at"])
        closed = datetime.fromisoformat(t["closed_at"])
        dates.append((opened, closed))
        entry_prices.append(t["entry_price"])
        close_prices.append(t["close_price"])
        sides.append(t["side"])
        pnls.append(t["pnl"])
        reasons.append(t["close_reason"])

    # Кумулятивный PnL
    cum_pnl = []
    running = 0
    cum_dates = []
    for i, t in enumerate(trades):
        running += t["pnl"]
        cum_pnl.append(running)
        cum_dates.append(datetime.fromisoformat(t["closed_at"]))

    fig, (ax_price, ax_pnl) = plt.subplots(
        2, 1, figsize=(14, 8),
        gridspec_kw={"height_ratios": [4, 1]},
        sharex=True,
    )

    # --- Верхний график: входы/выходы ---
    for i in range(len(trades)):
        opened, closed = dates[i]
        ep = entry_prices[i]
        cp = close_prices[i]
        color = "green" if pnls[i] > 0 else "red"

        # Линия от входа до выхода
        ax_price.plot([opened, closed], [ep, cp], color=color, alpha=0.4, linewidth=1)

        # Маркер входа
        if sides[i] == "buy":
            ax_price.plot(opened, ep, marker="^", color="green", markersize=10, zorder=5)
        else:
            ax_price.plot(opened, ep, marker="v", color="red", markersize=10, zorder=5)

        # Маркер выхода
        marker = "x" if reasons[i] == "sl_hit" else "o"
        ax_price.plot(closed, cp, marker=marker, color=color, markersize=8, zorder=5)

    ax_price.set_ylabel("Цена")
    title = f"Сделки ({timeframe})" if timeframe else "Сделки (все таймфреймы)"
    ax_price.set_title(title)
    ax_price.grid(True, alpha=0.3)
    ax_price.legend(
        handles=[
            plt.Line2D([0], [0], marker="^", color="green", linestyle="", markersize=8, label="Long вход"),
            plt.Line2D([0], [0], marker="v", color="red", linestyle="", markersize=8, label="Short вход"),
            plt.Line2D([0], [0], marker="o", color="gray", linestyle="", markersize=8, label="Выход (сигнал)"),
            plt.Line2D([0], [0], marker="x", color="gray", linestyle="", markersize=8, label="Выход (SL)"),
        ],
        loc="upper left", fontsize=8,
    )

    # --- Нижний график: кумулятивный PnL ---
    ax_pnl.fill_between(cum_dates, cum_pnl, 0,
                        where=[p >= 0 for p in cum_pnl], color="green", alpha=0.3)
    ax_pnl.fill_between(cum_dates, cum_pnl, 0,
                        where=[p < 0 for p in cum_pnl], color="red", alpha=0.3)
    ax_pnl.plot(cum_dates, cum_pnl, color="blue", linewidth=1.5)
    ax_pnl.axhline(y=0, color="gray", linestyle="--", linewidth=0.5)
    ax_pnl.set_ylabel("PnL (USDT)")
    ax_pnl.set_xlabel("Дата")
    ax_pnl.grid(True, alpha=0.3)

    ax_pnl.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
    fig.autofmt_xdate()
    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150)
        print(f"График сохранён: {save_path}")
    else:
        plt.show()


def main():
    parser = argparse.ArgumentParser(description="Dashboard торгового бота")
    parser.add_argument("--timeframe", "-t", type=str, default=None,
                        help="Фильтр по таймфрейму (4h, 15m)")
    parser.add_argument("--last", "-l", type=int, default=50,
                        help="Количество последних сделок (по умолчанию 50)")
    parser.add_argument("--save", "-s", type=str, default=None,
                        help="Сохранить график в файл (например chart.png)")
    parser.add_argument("--no-chart", action="store_true",
                        help="Только статистика, без графика")
    parser.add_argument("--db", type=str, default="trades.db",
                        help="Путь к базе данных")

    args = parser.parse_args()
    storage = TradeStorage(args.db)

    try:
        print_all_statistics(storage)

        if not args.no_chart:
            build_chart(storage, args.timeframe, args.last, args.save)
    finally:
        storage.close()


if __name__ == "__main__":
    main()
