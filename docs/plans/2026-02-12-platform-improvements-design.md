# Trading Platform Improvements — Design Document

**Date:** 2026-02-12
**Target:** Raspberry Pi `s1d18@192.168.50.13`, project `~/crypto_web`, port 5001
**Scale:** 14850 strategies, 5 coins (BTC/ETH/SOL/LTC/TON), timeframes 1m-1d

---

## 1. Positions — Pagination + Filters

### Problem
Page loads all ~3000 open positions at once. Browser freezes. No filtering.

### Solution

**Backend** — modify `/api/positions` in `api/app.py`:
- Add query params: `page` (default 1), `per_page` (default 50), `symbol`, `timeframe`, `direction`, `sort_by` (pnl, time, entry_price)
- SQL: `SELECT ... WHERE` filters `LIMIT per_page OFFSET (page-1)*per_page`
- Return `total_count`, `total_long`, `total_short`, `total_pages` in response (separate count query for summary — lightweight)
- PnL still calculated on frontend (needs live prices)

**Frontend** — modify `positions.html`:
- Add filter bar: Symbol (BTC/ETH/SOL/LTC/TON/All), Timeframe, Direction (Long/Short/All), Sort By
- Add pagination controls (prev/next + page numbers)
- Summary cards calculate from API totals, not page data
- Price refresh (2s) applies only to visible 50 rows

### Files to modify
- `api/app.py` — `/api/positions` endpoint
- `frontend/templates/positions.html` — filter bar, pagination UI, JS logic

---

## 2. History — Fix Filters

### Problem
Filter selects for "Result" and "Period" exist in HTML but are not connected to the API. `/api/trades` only accepts `category` and `limit`.

### Solution

**Backend** — modify `/api/trades` in `api/app.py`:
- Add params: `result` (win/loss/sl/signal/all), `period` (today/week/month/all), `symbol`, `timeframe`, `page`, `per_page`
- `result=win` → `WHERE pnl > 0`
- `result=loss` → `WHERE pnl < 0`
- `result=sl` → `WHERE close_reason = 'sl_hit'`
- `result=signal` → `WHERE close_reason = 'signal'`
- `period=today` → `WHERE closed_at >= date('now')`
- `period=week` → `WHERE closed_at >= date('now', '-7 days')`
- `period=month` → `WHERE closed_at >= date('now', '-30 days')`

**New endpoint** — `/api/trades/stats`:
- Same filters as `/api/trades`
- Returns aggregated stats: total_trades, wins, losses, win_rate, total_pnl, avg_pnl, best_trade, worst_trade, avg_duration, per-coin breakdown
- Frontend uses this for summary cards instead of calculating from page data

**Frontend** — modify `history.html`:
- Wire filter `<select>` elements to trigger API reload with params
- Summary stats fetched from `/api/trades/stats` with same filters
- Period filter options: All, Today, This Week, This Month

### Files to modify
- `api/app.py` — `/api/trades` endpoint + new `/api/trades/stats`
- `frontend/templates/history.html` — JS filter handlers

---

## 3. Analytics — Full Rebuild

### Problem
Only Top 10 / Bottom 10 by PnL. Loads all 14850 strategies client-side. No real analytics.

### Solution
Rebuild the `/analytics` page with 4 tabs. All aggregation on backend (Pi can't send 14850 records to browser efficiently).

### 3A. Dashboard Tab (default)

**Summary cards row:**
- Total Strategies | With Trades | Profitable | Losing
- Sum PnL | Avg PnL | Best Strategy | Worst Strategy

**Charts (using Chart.js — lightweight, no extra deps):**
- PnL by Coin — horizontal bar chart
- PnL by Timeframe — bar chart
- PnL by Direction — bar chart (Long vs Short vs Both)
- Win Rate Distribution — histogram (0-10%, 10-20%... 90-100%)

**Filters:** coin, direction (apply to all charts)

**Backend endpoint:** `GET /api/analytics/dashboard`
- Params: `symbol`, `direction`
- Returns: summary stats, pnl_by_coin[], pnl_by_timeframe[], pnl_by_direction[], winrate_distribution[]
- All aggregated server-side with SQL GROUP BY

### 3B. Heatmap Tab

**Heatmap matrix:**
- X axis: `st_multiplier` values (1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0)
- Y axis: `st_period` values (7, 8, 10, 12, 14, 16, 20)
- Cell color: avg PnL of strategies with those params (green→red gradient)
- Cell tooltip: avg PnL, count of strategies, avg win rate
- Click cell → navigate to filtered rating

**Filters:** coin, timeframe, direction

**Backend endpoint:** `GET /api/analytics/heatmap` (replace existing stub)
- Params: `symbol`, `timeframe`, `direction`
- Returns: `heatmap[][]` with {multiplier, period, avg_pnl, count, avg_winrate}
- SQL: parse params JSON, GROUP BY period+multiplier

### 3C. Rating Tab

**Filterable top-N table:**
- N selector: 10 / 25 / 50 / 100
- Sort by: PnL, Win Rate, Profit Factor, Sharpe, Max Drawdown, Trades Count (click column header)
- Filters: coin, timeframe, direction, min_trades (slider or input, default 3)
- Columns: Rank, Name, Symbol, TF, Dir, PnL, WR%, PF, Sharpe, DD, Trades, Open Pos

**Backend endpoint:** `GET /api/analytics/rating`
- Params: `symbol`, `timeframe`, `direction`, `sort_by`, `sort_dir`, `min_trades`, `limit`
- Returns: sorted list of strategies with all metrics
- SQL: JOIN strategies+trades, aggregate, HAVING trades >= min_trades, ORDER BY sort_by

### 3D. Group Comparison Tab

**Aggregated table — one row per group:**
- Group by selector: Timeframe, Direction, Coin, TF+Direction, Coin+TF
- Columns: Group, # Strategies, Avg PnL, Avg WR, Avg PF, Avg Sharpe, Total Trades, % Profitable
- Sort by any column
- Click row → drill down to rating filtered by that group

**Backend endpoint:** `GET /api/analytics/groups`
- Params: `group_by` (timeframe/direction/symbol/tf_direction/symbol_tf), `symbol`, `direction`
- Returns: aggregated rows
- SQL: GROUP BY selected dimension

### Files to modify/create
- `api/analytics.py` — rewrite all 4 endpoints (dashboard, heatmap, rating, groups)
- `frontend/templates/analytics.html` — full rewrite with tabs
- `frontend/static/js/analytics.js` — new file for analytics page logic
- Add Chart.js to `frontend/static/vendor/` or CDN link in `base.html`

---

## 4. Coin Dashboard — New Page

### New route: `/coin/<symbol>`

**Summary cards:**
- Total strategies for this coin | Currently in position | Long count | Short count | Sum PnL

**Consensus indicator (main widget):**
- Large gauge/donut: "73% strategies in LONG"
- Breakdown by TF: table showing per-timeframe consensus
- Auto-refresh every 10 seconds

**Best parameters table:**
- Top 5 param combinations (period, multiplier, sl%) by PnL for this coin
- Columns: Period, Multiplier, SL%, Avg PnL, # Strategies, Win Rate

**Recent trades:**
- Last 10 closed trades for this coin

**Backend endpoints:**
- `GET /api/coin/<symbol>/summary` — stats + consensus
- `GET /api/coin/<symbol>/best-params` — top 5 param combos
- `GET /api/coin/<symbol>/recent-trades` — last 10 trades

**Navigation:**
- Add link in sidebar next to each coin's watchlist link
- Or: add a tab/button on the watchlist page itself

### Files to modify/create
- `api/app.py` — add 3 new endpoints
- `frontend/templates/coin.html` — new template
- `frontend/static/js/coin.js` — new JS file
- `frontend/templates/base.html` — add sidebar navigation link

---

## Implementation Order

1. **Positions pagination + filters** — most impactful for usability (browser stops freezing)
2. **History filters** — small fix, quick win
3. **Analytics rebuild** — largest task, most value
4. **Coin dashboard** — new feature, depends on analytics endpoints being ready

---

## Technical Notes

- All aggregation on backend (SQL) — don't send 14850 records to browser
- Chart.js for charts (lightweight, ~60KB, no build step)
- Reuse existing glassmorphism CSS from base.html
- Heatmap can be pure CSS grid with colored divs (no library needed)
- All new endpoints follow existing pattern: return `{status: 'ok', ...}`
- Existing WebSocket infrastructure can be used for real-time updates on coin dashboard
