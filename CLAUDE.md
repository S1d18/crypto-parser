# CLAUDE.md

## Project Overview

**Снайпер** — скальпинг-бот для крипто-торговли (paper trading) на Bybit.
Сканирует топ-50 USDT-перпов по объёму, входит в быстрые сделки с x20 плечом.
Мульти-индикаторные сигналы (EMA+RSI+Volume+ADX), адаптивные SL/TP по ATR, trailing stop.

## Architecture

```
run.py              — Точка входа (бот + Flask сервер)
scalper/
├── config.py       — Dataclass Config, загрузка из .env
├── bot.py          — Главный asyncio торговый цикл
├── scanner.py      — Сканер топ-50 монет, ранжирование по силе сигнала
├── signals.py      — Мульти-индикаторные сигналы с адаптивным SL/TP
├── indicators.py   — Расчёт EMA, RSI, ATR, ADX, Volume Ratio (numpy)
├── filters.py      — Фильтр по тренду старшего ТФ (15m)
├── risk.py         — Trailing stop, позиционирование, лимиты убытков
├── exchange.py     — Async обёртка ccxt для Bybit
├── storage.py      — SQLite хранилище сделок и equity
└── web/
    ├── app.py      — Flask + SocketIO дашборд
    ├── templates/  — HTML (русский, glassmorphism)
    └── static/     — CSS/JS (real-time обновление)
```

## Environment Setup

```bash
.venv\Scripts\activate      # Windows
source .venv/bin/activate   # Linux/macOS
pip install -r requirements.txt
cp .env.example .env        # Заполнить API ключи Bybit (демо)
```

## Running

```bash
python run.py
```
Дашборд: **http://localhost:5001**

## Trading Parameters

- Баланс: $200, плечо x20
- На сделку: 50% баланса ($100 маржи = $2000 позиция)
- SL: адаптивный по ATR (1.5×ATR)
- TP: 2× расстояние SL
- Trailing stop подтягивается за ценой
- 10 убытков подряд → пауза 1 час
- Дневной лимит убытка: -$30 → стоп на день

## Testing

```bash
python -m pytest tests/ -v
```

## Key Dependencies

- `ccxt` — Bybit API (async)
- `numpy` — индикаторы
- `flask` + `flask-socketio` — веб-дашборд
- `python-dotenv` — загрузка .env
