"""Market microstructure data: order book, funding rate, open interest."""

import logging
import numpy as np

log = logging.getLogger(__name__)


class MarketData:
    """Fetches and analyzes order book, funding rate, OI for smarter exits."""

    def __init__(self, exchange):
        self._exchange = exchange

    async def get_exit_signals(self, symbol: str, direction: str) -> dict:
        """Analyze market data and return exit recommendations.

        Returns dict with:
            should_exit: bool — рекомендация закрыть позицию
            tighten_sl: bool — подтянуть стоп ближе
            reasons: list[str] — причины
            score: float — 0 (всё ок) to 1 (надо выходить)
        """
        signals = {
            'should_exit': False,
            'tighten_sl': False,
            'reasons': [],
            'score': 0.0,
        }

        score = 0.0

        # 1. Order Book — стена продаж/покупок
        try:
            ob = await self._exchange._exchange.fetch_order_book(symbol, limit=25)
            ob_signal = self._analyze_orderbook(ob, direction)
            score += ob_signal['score']
            signals['reasons'].extend(ob_signal['reasons'])
        except Exception:
            log.debug('Order book fetch failed for %s', symbol)

        # 2. Funding Rate
        try:
            fr = await self._exchange._exchange.fetch_funding_rate(symbol)
            fr_signal = self._analyze_funding(fr, direction)
            score += fr_signal['score']
            signals['reasons'].extend(fr_signal['reasons'])
        except Exception:
            log.debug('Funding rate fetch failed for %s', symbol)

        # 3. Open Interest
        try:
            oi_data = await self._exchange._exchange.fetch_open_interest_history(
                symbol, timeframe='5m', limit=10)
            oi_signal = self._analyze_oi(oi_data, direction)
            score += oi_signal['score']
            signals['reasons'].extend(oi_signal['reasons'])
        except Exception:
            log.debug('Open interest fetch failed for %s', symbol)

        signals['score'] = min(score, 1.0)

        # score >= 0.6 → подтянуть стоп, >= 0.8 → выходить
        if score >= 0.8:
            signals['should_exit'] = True
        elif score >= 0.5:
            signals['tighten_sl'] = True

        return signals

    def _analyze_orderbook(self, ob: dict, direction: str) -> dict:
        """Анализ стакана: есть ли стена против нас."""
        result = {'score': 0.0, 'reasons': []}

        bids = ob.get('bids', [])
        asks = ob.get('asks', [])
        if not bids or not asks:
            return result

        # Суммарный объём первых 10 уровней
        bid_volume = sum(b[1] for b in bids[:10])
        ask_volume = sum(a[1] for a in asks[:10])

        if bid_volume == 0 or ask_volume == 0:
            return result

        ratio = ask_volume / bid_volume if direction == 'long' else bid_volume / ask_volume

        # Если объём ПРОТИВ нас в 2+ раза больше — опасно
        if ratio > 3.0:
            result['score'] = 0.4
            result['reasons'].append(f'orderbook_wall({ratio:.1f}x)')
        elif ratio > 2.0:
            result['score'] = 0.2
            result['reasons'].append(f'orderbook_pressure({ratio:.1f}x)')

        return result

    def _analyze_funding(self, fr: dict, direction: str) -> dict:
        """Анализ funding rate: перегрев рынка."""
        result = {'score': 0.0, 'reasons': []}

        rate = fr.get('fundingRate')
        if rate is None:
            return result

        # Funding > 0.05% = рынок перегрет в лонгах
        # Funding < -0.05% = рынок перегрет в шортах
        if direction == 'long' and rate > 0.0005:
            result['score'] = 0.3
            result['reasons'].append(f'high_funding({rate*100:.3f}%)')
        elif direction == 'long' and rate > 0.001:
            result['score'] = 0.5
            result['reasons'].append(f'extreme_funding({rate*100:.3f}%)')
        elif direction == 'short' and rate < -0.0005:
            result['score'] = 0.3
            result['reasons'].append(f'negative_funding({rate*100:.3f}%)')
        elif direction == 'short' and rate < -0.001:
            result['score'] = 0.5
            result['reasons'].append(f'extreme_neg_funding({rate*100:.3f}%)')

        return result

    def _analyze_oi(self, oi_data: list, direction: str) -> dict:
        """Анализ Open Interest: резкое изменение = разворот."""
        result = {'score': 0.0, 'reasons': []}

        if not oi_data or len(oi_data) < 3:
            return result

        # OI values
        oi_values = []
        for item in oi_data:
            oi_val = item.get('openInterestAmount') or item.get('openInterestValue') \
                     or item.get('info', {}).get('openInterest')
            if oi_val is not None:
                oi_values.append(float(oi_val))

        if len(oi_values) < 3:
            return result

        # Изменение OI за последние 5 периодов
        recent = oi_values[-1]
        older = oi_values[0]
        if older == 0:
            return result

        change_pct = (recent - older) / older * 100

        # Резкое падение OI > 5% = массовое закрытие позиций → опасно
        if change_pct < -5:
            result['score'] = 0.4
            result['reasons'].append(f'oi_drop({change_pct:.1f}%)')
        # Резкий рост OI > 10% = новые позиции, возможен каскад ликвидаций
        elif change_pct > 10:
            result['score'] = 0.2
            result['reasons'].append(f'oi_spike({change_pct:.1f}%)')

        return result
