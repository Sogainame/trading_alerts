# Trading Alerts — Binance Pattern Scanner

Сканер технических паттернов на спот-рынке Binance с алертами в Telegram.

**Phase 1 (MVP):** топ-30 USDT пар, таймфрейм 5m, два детектора:
- **Volume Spike** — объём текущей свечи > 3× от среднего за 20 свечей
- **Engulfing** — поглощающая свеча с подтверждением объёмом > 1.5×

## Требования

- Python 3.10+
- macOS / Linux
- Системная библиотека TA-Lib (ставится отдельно от Python-пакета)

## Установка

### 1. Установить TA-Lib (системная C-библиотека)

**macOS:**
```bash
brew install ta-lib
```

**Linux (Ubuntu/Debian):**
```bash
wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz
tar -xzf ta-lib-0.4.0-src.tar.gz
cd ta-lib/
./configure --prefix=/usr
make
sudo make install
```

> Без этого шага `pip install TA-Lib` упадёт с ошибкой компиляции.

### 2. Клонировать проект и поставить Python-зависимости

```bash
git clone https://github.com/Sogainame/trading_alerts.git
cd trading_alerts

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt
```

### 3. Настроить `.env`

```bash
cp .env.example .env
```

Открыть `.env` и заполнить:

```
TELEGRAM_BOT_TOKEN=1234567890:AAH-bot-token-from-BotFather
TELEGRAM_CHAT_ID=123456789
```

**Где взять:**
- Токен — у [@BotFather](https://t.me/BotFather), команда `/newbot`
- Chat ID — после `/start` боту: открыть в браузере `https://api.telegram.org/bot<ТОКЕН>/getUpdates` и найти `"chat":{"id":...}`

### 4. Запуск

```bash
python main.py
```

В Telegram должно прийти сообщение `🟢 Scanner started`. Дальше ждём первый закрытый бар на одной из пар.

## Что бот делает по шагам

1. На старте через REST API получает топ-30 USDT-пар по 24h объёму на споте Binance
2. Подгружает по каждой паре последние ~50 закрытых свечей 5m (для расчёта средних)
3. Открывает один WebSocket с мультиплексной подпиской на kline-стримы всех пар
4. На событии "свеча закрыта" (`k.x == True`) прогоняет её через детекторы
5. Если паттерн найден И прошёл фильтры И не cooldown — шлёт алерт в Telegram
6. При падении WebSocket — перезапускается автоматически через 10 секунд

## Конфигурация

Все параметры в `config.py`:

| Параметр | Значение по умолчанию | Что делает |
|---|---|---|
| `TOP_N_PAIRS` | 30 | Сколько пар мониторим |
| `TIMEFRAME` | `"5m"` | Таймфрейм свечей |
| `CANDLE_BUFFER_SIZE` | 50 | Сколько свечей хранить в памяти |
| `VOLUME_SPIKE_MULTIPLIER` | 3.0 | Чувствительность Volume Spike |
| `VOLUME_AVG_PERIOD` | 20 | Сколько свечей для расчёта среднего объёма |
| `ENGULFING_VOLUME_MULTIPLIER` | 1.5 | Минимальный объём для Engulfing |
| `ALERT_COOLDOWN_SECONDS` | 1800 | Cooldown между алертами на одной паре (сек) |

## Структура проекта

```
trading_alerts/
├── main.py                    # entry point + auto-restart
├── config.py                  # все настройки
├── requirements.txt
├── .env.example
└── src/
    ├── data/
    │   ├── pairs.py           # топ USDT пар по объёму
    │   └── candle_buffer.py   # кольцевой буфер свечей
    ├── patterns/
    │   ├── volume_spike.py    # детектор Volume Spike
    │   └── engulfing.py       # детектор Engulfing
    ├── filters/
    │   └── cooldown.py        # анти-спам
    ├── notifier/
    │   └── telegram.py        # отправка в TG
    └── scanner.py             # основной asyncio loop
```

## Что важно понимать

- **Реагируем только на ЗАКРЫТЫЕ свечи** (`k.x == True`). Пока свеча не закрылась — её паттерн ещё может измениться, и сигнал на промежуточном тике = шум.
- **Volume Spike + Engulfing срабатывают одновременно — это сильнее**, чем по отдельности. В алерте оба будут перечислены.
- **Если Volume Spike и Engulfing указывают в разные стороны** — алерт не отправляется (внутреннее противоречие = не доверяем).

## Roadmap

- [ ] **Phase 2:** добавить таймфреймы 15m + 1h, мульти-TF подтверждение
- [ ] **Phase 2:** RSI divergence детектор (чаще даёт реальный эдж, чем геометрия)
- [ ] **Phase 2:** Breakout из консолидации
- [ ] **Phase 2:** скриншот графика в алерте (через mplfinance)
- [ ] **Phase 2:** Signal Scoring (0-100, фильтр по минимальной оценке)
- [ ] **Phase 3:** SQLite-лог всех сигналов + анализ точности (через 2 недели сбора данных)
- [ ] **Phase 3:** геометрические паттерны (H&S, треугольники, флаги)

## ⚠️ Дисклеймер

Бот **только присылает алерты**. Решения о входе, выходе, размере позиции и стопах — твои. Голый паттерн ≠ торговый сигнал. Используй с фильтрами по тренду, S/R уровням и риск-менеджментом.

Не торговая рекомендация.
