import pytest
from scalper.storage import Storage


@pytest.fixture
def store(tmp_path):
    db = tmp_path / "test.db"
    s = Storage(str(db))
    yield s
    s.close()


def test_open_and_close_trade(store):
    # Open a trade
    tid = store.open_trade(
        symbol="BTCUSDT",
        direction="long",
        qty=0.01,
        entry_price=50000.0,
        sl_price=48500.0,
        tp_price=51500.0,
        leverage=10,
        margin=50.0,
        reasons="supertrend_up",
    )
    assert isinstance(tid, int)

    # Verify it appears in open trades
    open_trades = store.get_open_trades()
    assert len(open_trades) == 1
    t = open_trades[0]
    assert t["symbol"] == "BTCUSDT"
    assert t["direction"] == "long"
    assert t["qty"] == 0.01
    assert t["entry_price"] == 50000.0
    assert t["status"] == "open"

    # Close the trade
    store.close_trade(
        trade_id=tid,
        exit_price=51000.0,
        pnl=10.0,
        pnl_pct=2.0,
        close_reason="tp",
    )

    # Verify no open trades remain
    assert len(store.get_open_trades()) == 0

    # Verify it appears in history
    history = store.get_trade_history(limit=10)
    assert len(history) == 1
    assert history[0]["close_reason"] == "tp"
    assert history[0]["pnl"] == 10.0


def test_daily_stats(store):
    tid = store.open_trade(
        symbol="BTCUSDT",
        direction="short",
        qty=0.05,
        entry_price=60000.0,
        sl_price=60600.0,
        tp_price=59400.0,
        leverage=5,
        margin=600.0,
        reasons="trend_down",
    )
    store.close_trade(tid, exit_price=59500.0, pnl=25.0, pnl_pct=4.17, close_reason="tp")

    stats = store.get_daily_stats()
    assert stats["total_trades"] == 1
    assert stats["total_pnl"] == 25.0
    assert stats["wins"] == 1
    assert stats["losses"] == 0
    assert stats["win_rate"] == 100.0

    # All stats should match for a single day
    all_stats = store.get_all_stats()
    assert all_stats["total_trades"] == 1
    assert all_stats["total_pnl"] == 25.0


def test_equity_snapshot(store):
    store.save_equity_snapshot(1000.0)
    store.save_equity_snapshot(1025.0)

    history = store.get_equity_history()
    assert len(history) == 2
    assert history[0]["balance"] == 1000.0
    assert history[1]["balance"] == 1025.0
    # Each entry should have a timestamp
    assert "timestamp" in history[0]
    assert "timestamp" in history[1]
