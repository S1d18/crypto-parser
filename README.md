# Crypto Parser
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)

Платформа для алгоритмической торговли криптовалютой на бирже Bybit с веб-дашбордом в реальном времени.

## Возможности

- Live-торговля на Bybit (фьючерсы USDT-Perpetual)
- Стратегия Supertrend на двух таймфреймах (4h Long + 10m Short)
- Paper-trading: 20+ виртуальных стратегий для бэктестинга
- Веб-дашборд с real-time обновлениями (WebSocket)
- Мониторинг цен с 10 бирж одновременно
- Аналитика и сравнение стратегий
- История сделок и позиций
- Telegram-уведомления

## Технологии

- Python 3.11+
- Flask / Flask-SocketIO
- ccxt — подключение к биржам
- NumPy / Pandas — расчёты индикаторов
- SQLite — хранение сделок
- Eventlet — async WebSocket
- Matplotlib — графики аналитики

## Установка

```bash
git clone https://github.com/<username>/crypto-parser.git
cd crypto-parser
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
pip install -r requirements.txt
```

## Настройка

Создайте файл `.env` (см. `.env.example`):
```
BYBIT_API_KEY=your-bybit-api-key
BYBIT_API_SECRET=your-bybit-api-secret
BYBIT_DEMO=true
TELEGRAM_TOKEN=your-telegram-bot-token
TELEGRAM_CHAT_ID=your-chat-id
```

## Запуск

### Веб-дашборд
```bash
python -m api.app
```

### Live-бот
```bash
python -m strategies.live.supertrend_bot
```

## Архитектура

```
crypto-parser/
├── core/
│   ├── supertrend.py      # Расчёт индикатора Supertrend
│   ├── config.py          # Конфигурация из .env
│   ├── database.py        # Схема БД
│   ├── price_service.py   # Агрегация цен с бирж
│   └── notifier.py        # Telegram-уведомления
├── strategies/
│   ├── live/              # Live-стратегии
│   └── paper/             # Paper-стратегии (20+)
├── api/
│   ├── app.py             # Flask приложение
│   ├── live.py            # API live-торговли
│   └── websocket.py       # WebSocket обновления
└── frontend/
    ├── templates/         # HTML шаблоны
    └── static/            # CSS, JS
```
