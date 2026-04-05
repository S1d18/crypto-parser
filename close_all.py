"""Close ALL open positions on Bybit by market order.

Usage:
    python close_all.py          # dry run (shows what would close)
    python close_all.py --exec   # actually close everything
"""

import sys
import ccxt

try:
    from dotenv import load_dotenv
except ImportError:
    pass
else:
    load_dotenv()

import os


def main():
    dry_run = '--exec' not in sys.argv

    api_key = os.getenv('BYBIT_API_KEY', '')
    api_secret = os.getenv('BYBIT_API_SECRET', '')
    demo = os.getenv('BYBIT_DEMO', 'true').lower() in ('true', '1', 'yes')

    if not api_key or not api_secret:
        print('ERROR: BYBIT_API_KEY / BYBIT_API_SECRET not set in .env')
        sys.exit(1)

    exchange = ccxt.bybit({
        'apiKey': api_key,
        'secret': api_secret,
        'options': {'defaultType': 'swap'},
        'enableRateLimit': True,
    })

    if demo:
        exchange.enable_demo_trading(True)
        print('Mode: DEMO')
    else:
        print('Mode: REAL')

    exchange.load_markets()

    # Fetch all open positions
    positions = exchange.fetch_positions()
    open_positions = [p for p in positions if p['contracts'] and p['contracts'] > 0]

    if not open_positions:
        print('\nNo open positions. Nothing to close.')
        return

    print(f'\nFound {len(open_positions)} open position(s):\n')

    for p in open_positions:
        side = p['side']  # 'long' or 'short'
        symbol = p['symbol']
        qty = p['contracts']
        entry = p.get('entryPrice', 0)
        pnl = p.get('unrealizedPnl', 0)
        mark = p.get('markPrice', 0)

        print(f'  {symbol:25s} {side:5s}  qty={qty}  entry=${entry}  mark=${mark}  uPnL=${pnl:.2f}')

    if dry_run:
        print('\n--- DRY RUN --- Add --exec to actually close all positions')
        return

    print('\nClosing all positions...\n')

    for p in open_positions:
        symbol = p['symbol']
        side = p['side']
        qty = p['contracts']

        # Close = opposite side with reduceOnly
        close_side = 'sell' if side == 'long' else 'buy'

        try:
            qty = exchange.amount_to_precision(symbol, qty)
            order = exchange.create_order(
                symbol=symbol,
                type='market',
                side=close_side,
                amount=float(qty),
                params={'reduceOnly': True},
            )
            fill_price = order.get('average') or order.get('price') or '?'
            print(f'  CLOSED {symbol} {side} qty={qty} @ {fill_price}')
        except Exception as e:
            print(f'  FAILED {symbol}: {e}')

    print('\nDone.')


if __name__ == '__main__':
    main()
