import urllib.request, json

base = "http://localhost:5001/api/coin"

# 1. Summary
for coin in ['BTC', 'ETH', 'SOL']:
    print(f"\n=== {coin} SUMMARY ===")
    data = json.load(urllib.request.urlopen(f"{base}/{coin}/summary"))
    print(f"Strategies: {data['total_strategies']} (L:{data['long_strategies']} S:{data['short_strategies']} B:{data['both_strategies']})")
    c = data['consensus']
    print(f"Consensus: {c['open_total']} open ({c['open_long']}L / {c['open_short']}S), Long={c['long_pct']}% Short={c['short_pct']}%")
    print(f"PnL: ${data['sum_pnl']}, Trades: {data['total_trades']}, WR: {data['win_rate']}%")
    print(f"TF breakdown ({len(data['tf_consensus'])} timeframes):")
    for tf in data['tf_consensus'][:4]:
        print(f"  {tf['timeframe']}: {tf['total']} strats, {tf['in_long']}L/{tf['in_short']}S, PnL=${tf.get('pnl',0)}")

# 2. Best Params
print("\n=== BTC BEST PARAMS ===")
data = json.load(urllib.request.urlopen(f"{base}/BTC/best-params"))
print(f"Top {data['count']} param combos:")
for p in data['params'][:5]:
    print(f"  P={p['period']} M={p['multiplier']} SL={p['sl_percent']}% -> avg_pnl=${p['avg_pnl']} WR={p['avg_winrate']}% ({p['strategies']} strats)")

# 3. Recent Trades
print("\n=== BTC RECENT TRADES ===")
data = json.load(urllib.request.urlopen(f"{base}/BTC/recent-trades"))
print(f"Last {data['count']} trades:")
for t in data['trades'][:5]:
    pnl = t['pnl'] or 0
    print(f"  {t['closed_at'][:16]} {t['strategy_name'][:30]} {t['side']} {t['close_reason']} ${pnl:.4f}")

# 4. Page loads
print("\n=== PAGE CHECK ===")
resp = urllib.request.urlopen("http://localhost:5001/coin/BTC")
html = resp.read().decode()
print(f"Page size: {len(html)} bytes")
print(f"Has Chart.js: {'chart.js' in html}")
print(f"Has consensusChart: {'consensusChart' in html}")

# 5. Sidebar check
resp = urllib.request.urlopen("http://localhost:5001/analytics")
html = resp.read().decode()
print(f"Sidebar has Coin Dashboards: {'Coin Dashboards' in html}")
print(f"Sidebar has /coin/BTC: {'/coin/BTC' in html}")
