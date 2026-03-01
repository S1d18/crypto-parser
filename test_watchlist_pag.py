import urllib.request, json, time

base = "http://localhost:5001/api/strategies"

# 1. Test paginated endpoint — page 1
print("=== BTC PAGE 1 ===")
t0 = time.time()
data = json.load(urllib.request.urlopen(f"{base}/list?symbol=BTC&page=1&per_page=100"))
t1 = time.time()
print(f"Time: {t1-t0:.2f}s")
print(f"Page {data['page']}/{data['total_pages']}, Total: {data['total']}")
print(f"Returned: {len(data['strategies'])} strategies")
print(f"Summary: total={data['summary']['total']}, running={data['summary']['running']}, open_pos={data['summary']['open_positions']}, pnl=${data['summary']['sum_pnl']}")
print(f"Groups: {data['group_counts']}")
if data['strategies']:
    s = data['strategies'][0]
    print(f"First: {s['name']} pnl=${s['total_pnl']} wr={s['win_rate']}% trades={s['trades_count']} open={s['open_trades']}")

# 2. Test page 2
print("\n=== BTC PAGE 2 ===")
data2 = json.load(urllib.request.urlopen(f"{base}/list?symbol=BTC&page=2&per_page=100"))
print(f"Page {data2['page']}/{data2['total_pages']}, Returned: {len(data2['strategies'])}")
if data2['strategies']:
    print(f"First: {data2['strategies'][0]['name']}")

# 3. Test with group filter
print("\n=== BTC SCALPING ===")
data3 = json.load(urllib.request.urlopen(f"{base}/list?symbol=BTC&group=scalping"))
print(f"Total: {data3['total']}, Pages: {data3['total_pages']}, Returned: {len(data3['strategies'])}")

# 4. Test with timeframe filter
print("\n=== BTC 5m only ===")
data4 = json.load(urllib.request.urlopen(f"{base}/list?symbol=BTC&timeframe=5m"))
print(f"Total: {data4['total']}, Pages: {data4['total_pages']}")

# 5. Compare speed: old vs new
print("\n=== SPEED COMPARISON ===")
t0 = time.time()
json.load(urllib.request.urlopen(f"{base}/list?symbol=BTC&page=1&per_page=100"))
t_new = time.time() - t0

t0 = time.time()
json.load(urllib.request.urlopen(f"{base}/all"))
t_old = time.time() - t0

print(f"New (100 BTC): {t_new:.2f}s")
print(f"Old (all 14850): {t_old:.2f}s")
print(f"Speedup: {t_old/t_new:.1f}x")

# 6. Page loads
print("\n=== PAGE CHECK ===")
html = urllib.request.urlopen("http://localhost:5001/watchlist/btc").read().decode()
print(f"Page size: {len(html)} bytes")
print(f"Has pagination-controls: {'pagination-controls' in html}")
print(f"Has /api/strategies/list: {'strategies/list' in html}")
