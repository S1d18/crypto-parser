from dataclasses import dataclass


@dataclass
class PaperStrategyConfig:
    strategy_id: str
    group: str          # "scalping", "intraday", "swing", "position"
    timeframe: str
    direction: str      # "long", "short", "both"
    st_period: int
    st_multiplier: float
    sl_percent: float
    virtual_balance: float = 10_000.0


PAPER_STRATEGIES: list[PaperStrategyConfig] = [
    # --- Группа A: Scalping (5m, 15m) ---
    PaperStrategyConfig("scalp_5m_short_fast",  "scalping", "5m",  "short", 7,  2.0, 0.5),
    PaperStrategyConfig("scalp_5m_short_std",   "scalping", "5m",  "short", 10, 3.0, 1.0),
    PaperStrategyConfig("scalp_15m_short_fast", "scalping", "15m", "short", 7,  2.0, 0.75),
    PaperStrategyConfig("scalp_15m_short_std",  "scalping", "15m", "short", 10, 3.0, 1.0),
    PaperStrategyConfig("scalp_15m_both_tight", "scalping", "15m", "both",  8,  1.5, 0.5),

    # --- Группа B: Intraday (30m, 1h) ---
    PaperStrategyConfig("intra_30m_long_wide",   "intraday", "30m", "long",  14, 3.5, 2.0),
    PaperStrategyConfig("intra_30m_short_tight", "intraday", "30m", "short", 10, 2.0, 1.5),
    PaperStrategyConfig("intra_1h_long_std",     "intraday", "1h",  "long",  10, 3.0, 2.0),
    PaperStrategyConfig("intra_1h_long_slow",    "intraday", "1h",  "long",  20, 4.0, 2.5),
    PaperStrategyConfig("intra_1h_both_mid",     "intraday", "1h",  "both",  12, 2.5, 1.5),

    # --- Группа C: Swing (2h, 4h, 6h) ---
    PaperStrategyConfig("swing_2h_long_std",  "swing", "2h", "long", 10, 3.0, 2.5),
    PaperStrategyConfig("swing_2h_both_fast", "swing", "2h", "both", 8,  2.0, 2.0),
    PaperStrategyConfig("swing_4h_long_std",  "swing", "4h", "long", 10, 3.0, 3.0),
    PaperStrategyConfig("swing_4h_long_slow", "swing", "4h", "long", 14, 3.5, 4.0),
    PaperStrategyConfig("swing_4h_both_wide", "swing", "4h", "both", 12, 4.0, 5.0),
    PaperStrategyConfig("swing_6h_long_std",  "swing", "6h", "long", 10, 3.0, 3.5),

    # --- Группа D: Position (12h, 1d) ---
    PaperStrategyConfig("pos_12h_long_std",  "position", "12h", "long", 10, 3.0, 4.0),
    PaperStrategyConfig("pos_12h_long_slow", "position", "12h", "long", 16, 3.5, 5.0),
    PaperStrategyConfig("pos_1d_long_std",   "position", "1d",  "long", 10, 3.0, 5.0),
    PaperStrategyConfig("pos_1d_both_wide",  "position", "1d",  "both", 14, 4.0, 5.0),
]
