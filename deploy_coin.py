"""
Deploy script: register coin_bp blueprint + add /coin/<symbol> route + update sidebar.
Run on Pi: python3 deploy_coin.py
"""
import re

APP_PATH = '/home/s1d18/crypto_web/api/app.py'
BASE_PATH = '/home/s1d18/crypto_web/frontend/templates/base.html'

# ===========================================
# 1. Add coin blueprint registration to app.py
# ===========================================
with open(APP_PATH, 'r') as f:
    app_code = f.read()

# Add coin route if not already present
if '/coin/<symbol>' not in app_code:
    # Add route BEFORE the register_blueprints function
    route_code = '''
@app.route('/coin/<symbol>')
def coin_dashboard(symbol):
    """Coin Dashboard page."""
    valid_symbols = ['btc', 'eth', 'sol', 'ltc', 'ton']
    if symbol.lower() not in valid_symbols:
        return "Invalid symbol", 404
    return render_template('coin.html', symbol=symbol.upper())

'''
    # Insert after the strategies_catalog route
    marker = "@app.route('/strategies')\ndef strategies_catalog():\n    \"\"\"Каталог всех стратегий.\"\"\"\n    return render_template('strategies.html')"
    if marker in app_code:
        app_code = app_code.replace(marker, marker + '\n\n' + route_code)
        print("[OK] Added /coin/<symbol> route to app.py")
    else:
        print("[WARN] Could not find marker for route insertion, trying alternative...")
        # Try inserting before register_blueprints
        alt_marker = "# ============================================================\n# Health check"
        if alt_marker in app_code:
            app_code = app_code.replace(alt_marker, route_code + '\n' + alt_marker)
            print("[OK] Added /coin/<symbol> route (alt location)")
        else:
            print("[ERROR] Could not find insertion point for route!")
else:
    print("[SKIP] /coin/<symbol> route already exists")

# Add coin_bp blueprint registration
if 'coin_bp' not in app_code:
    old_bp = """    try:
        from api.analytics import analytics_bp
        app.register_blueprint(analytics_bp, url_prefix='/api/analytics')
        logger.info("✓ Registered blueprint: /api/analytics")
    except ImportError as e:
        logger.warning(f"Could not register analytics_bp: {e}")"""

    new_bp = old_bp + """

    try:
        from api.coin import coin_bp
        app.register_blueprint(coin_bp, url_prefix='/api/coin')
        logger.info("✓ Registered blueprint: /api/coin")
    except ImportError as e:
        logger.warning(f"Could not register coin_bp: {e}")"""

    if old_bp in app_code:
        app_code = app_code.replace(old_bp, new_bp)
        print("[OK] Added coin_bp blueprint registration")
    else:
        print("[ERROR] Could not find analytics_bp registration block!")
else:
    print("[SKIP] coin_bp already registered")

with open(APP_PATH, 'w') as f:
    f.write(app_code)

# ===========================================
# 2. Update sidebar in base.html
# ===========================================
with open(BASE_PATH, 'r') as f:
    base_code = f.read()

if '/coin/' not in base_code:
    # Add "Coin Dashboards" section after Watchlists section
    old_nav = """                <div class="nav-section">
                    <div class="nav-section-title">Management</div>"""

    coin_nav = """                <div class="nav-section">
                    <div class="nav-section-title">Coin Dashboards</div>
                    <a href="/coin/BTC" class="nav-item">
                        <i data-lucide="target"></i>
                        <span>BTC Dashboard</span>
                    </a>
                    <a href="/coin/ETH" class="nav-item">
                        <i data-lucide="target"></i>
                        <span>ETH Dashboard</span>
                    </a>
                    <a href="/coin/SOL" class="nav-item">
                        <i data-lucide="target"></i>
                        <span>SOL Dashboard</span>
                    </a>
                    <a href="/coin/LTC" class="nav-item">
                        <i data-lucide="target"></i>
                        <span>LTC Dashboard</span>
                    </a>
                    <a href="/coin/TON" class="nav-item">
                        <i data-lucide="target"></i>
                        <span>TON Dashboard</span>
                    </a>
                </div>

                <div class="nav-section">
                    <div class="nav-section-title">Management</div>"""

    if old_nav in base_code:
        base_code = base_code.replace(old_nav, coin_nav)
        print("[OK] Added Coin Dashboards section to sidebar")
    else:
        print("[ERROR] Could not find Management section in base.html!")
else:
    print("[SKIP] Coin links already in sidebar")

with open(BASE_PATH, 'w') as f:
    f.write(base_code)

print("\n[DONE] Deploy script completed.")
