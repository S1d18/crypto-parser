import urllib.request, json

base = "http://localhost:5001/api/analytics"

# 1. Dashboard
print("=== DASHBOARD ===")
data = json.load(urllib.request.urlopen(f"{base}/dashboard"))
s = data['summary']
print(f"Strategies: {s['total_strategies']}, With trades: {s['with_trades']}")
print(f"Profitable: {s['profitable']}, Losing: {s['losing']}")
print(f"Sum PnL: ${s['sum_pnl']}, Avg PnL: ${s['avg_pnl']}")
if s['best_strategy']:
    print(f"Best: {s['best_strategy']['name']} ${s['best_strategy']['pnl']}")
print(f"Coins: {[c['coin'] + ':$' + str(c['pnl']) for c in data['pnl_by_coin']]}")
print(f"TFs: {[t['timeframe'] + ':$' + str(t['pnl']) for t in data['pnl_by_timeframe'][:5]]}...")
print(f"Dirs: {[d['direction'] + ':$' + str(d['pnl']) for d in data['pnl_by_direction']]}")
print(f"WR dist: {data['winrate_distribution']}")

# 2. Heatmap
print("\n=== HEATMAP ===")
data = json.load(urllib.request.urlopen(f"{base}/heatmap"))
print(f"Cells: {len(data['cells'])}, Periods: {data['periods']}, Multipliers: {data['multipliers']}")
if data['cells']:
    c = data['cells'][0]
    print(f"First: period={c['period']} mult={c['multiplier']} avg_pnl=${c['avg_pnl']} count={c['count']}")

# 3. Rating
print("\n=== RATING ===")
data = json.load(urllib.request.urlopen(f"{base}/rating?limit=5&sort_by=total_pnl&sort_dir=desc"))
print(f"Top {data['count']} strategies:")
for s in data['strategies']:
    print(f"  {s['name']}: PnL=${s['total_pnl']} WR={s['win_rate']}% PF={s['profit_factor']} trades={s['trades']}")

# 4. Groups
print("\n=== GROUPS ===")
data = json.load(urllib.request.urlopen(f"{base}/groups?group_by=timeframe"))
print(f"By timeframe ({data['count']} groups):")
for g in data['groups'][:5]:
    print(f"  {g['name']}: {g['strategies']} strats, avg_pnl=${g['avg_pnl']}, WR={g['avg_winrate']}%")

# 5. Filtered
print("\n=== FILTERED: BTC only ===")
data = json.load(urllib.request.urlopen(f"{base}/dashboard?symbol=BTC"))
s = data['summary']
print(f"BTC strategies: {s['total_strategies']}, PnL: ${s['sum_pnl']}")
