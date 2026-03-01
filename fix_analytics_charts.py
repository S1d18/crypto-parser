"""Fix analytics charts: constrain chart height inside .chart-box."""

PATH = '/home/s1d18/crypto_web/frontend/templates/analytics.html'

with open(PATH, 'r') as f:
    code = f.read()

# 1. Fix CSS: add height constraint to .chart-box
old_css = """.chart-box {
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 1rem;
}
.chart-box h3 { font-size: 0.9rem; margin-bottom: 0.75rem; color: var(--text-muted); }"""

new_css = """.chart-box {
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 1rem;
}
.chart-box h3 { font-size: 0.9rem; margin-bottom: 0.75rem; color: var(--text-muted); }
.chart-wrap {
    position: relative;
    height: 260px;
    width: 100%;
}"""

if old_css in code:
    code = code.replace(old_css, new_css)
    print("[OK] Added .chart-wrap CSS with fixed height")
else:
    print("[ERROR] Could not find .chart-box CSS")

# 2. Wrap each canvas in a .chart-wrap div
canvases = [
    ('chart-coin', 'PnL по монетам'),
    ('chart-tf', 'PnL по таймфреймам'),
    ('chart-dir', 'PnL по направлению'),
    ('chart-wr', 'Распределение Win Rate'),
]
for canvas_id, title in canvases:
    old_canvas = f"""<div class="chart-box">
                <h3>{title}</h3>
                <canvas id="{canvas_id}" height="250"></canvas>
            </div>"""
    new_canvas = f"""<div class="chart-box">
                <h3>{title}</h3>
                <div class="chart-wrap"><canvas id="{canvas_id}"></canvas></div>
            </div>"""
    if old_canvas in code:
        code = code.replace(old_canvas, new_canvas)
        print(f"[OK] Wrapped {canvas_id} in .chart-wrap")
    else:
        print(f"[WARN] Could not find canvas {canvas_id}")

with open(PATH, 'w') as f:
    f.write(code)

print("\n[DONE]")
