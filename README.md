# Bybit Futures Signal Engine — MVP v1

Production-oriented MVP quantitative engine for 24/7 monitoring, multi-timeframe feature extraction, composite scoring, and paper tracking on **Bybit USDT Perpetual Futures** (V5 API).

---

## 1. Назначение системы

Система разработана для непрерывного мониторинга рынка криптовалютных деривативов Bybit:
- **Автоматический dynamic universe selection** (TOP-20 ликвидных пар) на основе turnover, open interest, volume, spread, volatility и trade activity.
- **Многотаймфреймовый анализ**: 4H (HTF контекст), 1H (структура рынка), 15m (сетап), 5m (уточнение входа).
- **Строгое отсутствие look-ahead bias**: технические индикаторы и паттерны структуры рассчитываются исключительно по закрытым барам (`confirm: true`).
- **Комплексный скоринг (0–100)**: объединение тренда, структуры (BOS/CHOCH), сбора ликвидности, моментума, объемов, волатильности, деривативов (OI, Funding) и Price Action.
- **Telegram оповещения**: отправка только валидированных сетапов со `Score >= 75` и `Directional Edge >= 5` с контролем анти-спама (cooldown).
- **Paper Result Tracking**: симуляция и учет результатов (TP1, TP2, Stop Loss, MFE, MAE) с консервативной обработкой неоднозначных свечей.
- **Строгое ограничение**: система **НЕ** совершает реальных сделок и **НЕ** использует торговых API-ключей.

---

## 2. Архитектура и компоненты

```
bybit_signal_engine/
├── app/
│   ├── main.py                  # Главная точка входа и оркестратор
│   ├── config.py                # Pydantic настройки и загрузчик YAML
│   ├── exchange/
│   │   ├── base.py              # Интерфейс ExchangeAdapter
│   │   └── bybit.py             # Bybit V5 реализация
│   ├── market_data/
│   │   ├── rest.py              # Bybit REST клиент (пагинация, backoff, rate limits)
│   │   ├── websocket.py         # Bybit V5 Public WS (reconnect, heartbeat, batching)
│   │   ├── provider.py          # Абстракция MarketDataProvider (Live / Historical)
│   │   ├── historical.py        # Исторический провайдер для бэктестов
│   │   └── ranking.py           # Мультифакторный ранжировщик Dynamic TOP-20
│   ├── database/
│   │   ├── models.py            # SQLAlchemy модели (SQLite)
│   │   └── repository.py        # Асинхронный репозиторий персистентности
│   ├── indicators/              # Квантовые индикаторы (EMA, RSI, ATR, VWAP)
│   ├── analysis/                # Price Action, Derivatives, Regime, Scoring, Paper Tracking
│   ├── telegram/
│   │   └── bot.py               # Telegram Dispatcher с анти-спамом
│   ├── backtest/
│   │   └── interface.py         # Интерфейс бэктест-движка
│   └── utils/
│       ├── logging.py           # Консольный логгер с миллисекундами UTC
│       ├── rate_limiter.py      # Async Token Bucket
│       └── retry.py             # Экспоненциальный retry с jitter
├── config/
│   ├── scoring.yaml             # Веса факторов и пороги скоринга
│   └── ranking.yaml             # Коэффициенты мультифакторного отбора пар
├── tests/                       # Pytest unit и integration тесты
├── data/                        # SQLite база данных signals.db
├── Dockerfile                   # Production Docker образ
├── docker-compose.yml           # Конфигурация для запуска 24/7
├── requirements.txt             # Зависимости Python 3.12+
└── README.md
```

---

## 3. Установка и запуск

### 3.1. Локальный запуск

1. **Клонируйте репозиторий и создайте venv**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Настройте переменные окружения**:
   ```bash
   cp .env.example .env
   # Укажите TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID (при необходимости)
   ```

3. **Запустите тесты**:
   ```bash
   pytest tests -v
   ```

4. **Запустите программу**:
   ```bash
   python3 -m app.main
   ```

---

### 3.2. Запуск в Docker (24/7 Production)

```bash
docker compose up -d --build
```

- **Просмотр логов**:
  ```bash
  docker compose logs -f bybit-signal-engine
  ```
- **Остановка**:
  ```bash
  docker compose down
  ```

---

## 4. Конфигурация параметров

- `TOP_SYMBOLS` (по умолчанию `20`): количество активных пар в мониторинге.
- `MIN_SCORE` (по умолчанию `75`): минимальный балл для формирования сигнала.
- `MIN_DIRECTIONAL_EDGE` (по умолчанию `5`): минимальная разница между `long_score` и `short_score`.
- `SIGNAL_COOLDOWN_MINUTES` (по умолчанию `20`): окно анти-спама для одинаковых сетапов.
- `AMBIGUOUS_CANDLE_POLICY` (`conservative`): если в одной свече коснулись и TP, и SL, консервативно фиксируется SL.
