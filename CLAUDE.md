# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Торговый бот Supertrend для BTCUSDT на Bybit. Использует индикатор Supertrend (10, 3) на двух таймфреймах:
- **4h Long-only** — основная стратегия (SL=3%)
- **10m Short-only** — хедж (SL=1%)

## Architecture

```
config.py       — Dataclass Config, загрузка из .env
supertrend.py   — Расчёт индикатора Supertrend (ATR-based)
bot.py          — Главный торговый бот (точка входа), asyncio цикл
notifier.py     — Telegram-уведомления
storage.py      — SQLite хранилище сделок
dashboard.py    — CLI-графики (matplotlib)

web/            — Веб-интерфейс (Flask, порт 5001)
├── app.py      — Flask приложение с API endpoints
├── run.py      — Запуск веб-сервера
├── templates/  — HTML шаблоны (glassmorphism дизайн)
└── static/     — CSS и JavaScript (real-time updates)

arb/            — Арбитражный дашборд (отдельный проект, порт 5001)
```

## Environment Setup

```bash
# Активация виртуального окружения
.venv\Scripts\activate      # Windows
source .venv/bin/activate   # Linux/macOS

# Установка зависимостей
pip install -r requirements.txt

# Настройка
cp .env.example .env        # Заполнить API ключи
```

## Running

### Торговый бот
```bash
python bot.py
```

### Веб-интерфейс мониторинга
```bash
cd web
python run.py
```
Откройте: **http://localhost:5001**

Веб-дашборд показывает:
- Статус бота и текущие позиции (4h Long / 10m Short)
- Статистику: общий PnL, винрейт, количество сделок
- Историю сделок с фильтрами
- Современный дизайн с glassmorphism и Lucide иконками
- Real-time обновление каждые 5 секунд

## Key Dependencies

- `ccxt` — подключение к Bybit API
- `numpy` — расчёт ATR/Supertrend
- `python-dotenv` — загрузка .env
- `requests` — Telegram API
