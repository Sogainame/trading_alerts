# Trading Alerts v2 — Multi-Detector Pattern Scanner

Real-time сканер импульсов на спот-рынке Binance с системой множественных подтверждений и скоринга.

## Архитектура

5 параллельных детекторов работают **независимо**, каждый выдаёт сигнал со своим вкладом в общий score. Алерт срабатывает только когда сумма очков ≥ порога.

| Детектор | Источник данных | Вес | Что ловит |
|---|---|---|---|
| **Velocity** | aggTrade stream | +25 | Цена изменилась на ≥0.5% за 30 секунд |
| **Taker Imbalance** | aggTrade stream | +20 | ≥70% объёма за 60с — market buys (или sells) |
| **Whale Trades** | aggTrade stream | +20 | 3+ сделок ≥$50k за 60с в одну сторону |
| **Volume Anomaly** | kline 5m (in-progress) | +15 | Незакрытая 5m свеча уже накопила ≥2× средний объём |
| **Multi-TF Pattern** | kline 5m + 1h | +25 | Engulfing 5m + объём + EMA50 на 1h в ту же сторону |

### Скоринг и тиры

```
Score = Σ score_contribution однонаправленных сигналов − противоположные

≥ 85 → 🔥 PREMIUM (4-5 сигналов совпали — сильнейший edge)
≥ 70 → 🟢 STRONG  (3-4 сигнала — качественный сигнал)
≥ 50 → 🟡 WATCH   (1-2 сигнала — обрати внимание)
< 50 → не алертим
```

## Скоростные оптимизации

- **Один WebSocket connection** на все потоки (combined stream multiplex до 1024 streams в одном TCP)
- **`compression=None`** — не тратим CPU на gzip, нужны микросекунды
- **Lock-free in-memory state** — один event loop, никаких threads/Lock'ов
- **Direct `websockets` library** вместо python-binance — на 2-3 ms быстрее на сообщение
- **Async SQLite** через aiosqlite — лог не блокирует горячий путь
- **Hot-path detectors** работают на rolling deque — O(1) append, O(N) расчёт по фиксированному окну

End-to-end latency: ~150-300 ms (от trade на Binance до уведомления в Telegram), зависит от пинга до Tokyo AWS.

## Что приходит в Telegram

```
🟢 STRONG • SOLUSDT • Score 78
Направление: ВВЕРХ
Цена: 165.42
━━━━━━━━━━━━━━━━━━━━
✅ +1.2% за 30s  (+25)
✅ Takers: 78% buys (60s)  (+20)
✅ 4 whale buys ≥$50k за 60s ($240k)  (+20)
✅ Vol 2.1x avg (intra-5m, ещё не закрылась)  (+15)
```

Через **5/15/30 минут** на это сообщение прилетают reply-апдейты с %изменения цены — для последующего анализа точности.

## Установка

### 1. TA-Lib (системная C-библиотека)

**macOS:**
```bash
brew install ta-lib
```

**Linux:**
```bash
wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz
tar -xzf ta-lib-0.4.0-src.tar.gz && cd ta-lib/
./configure --prefix=/usr && make && sudo make install
```

### 2. Клонировать и поставить Python deps

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

Содержимое `.env`:
```
TELEGRAM_BOT_TOKEN=токен_от_BotFather
TELEGRAM_CHAT_ID=твой_chat_id
```

### 4. Запуск

```bash
caffeinate -i python main.py    # macOS, чтобы мак не спал
# или
python main.py
```

## Структура проекта

```
trading_alerts/
├── main.py                          # entry + auto-restart
├── config.py                        # все веса и пороги
├── data/
│   └── signals.db                   # SQLite log (gitignored)
└── src/
    ├── core/
    │   └── state.py                 # Trade, Candle, SymbolState, GlobalState
    ├── data/
    │   ├── binance_rest.py          # лёгкий REST клиент (httpx)
    │   ├── pairs.py                 # топ USDT пар
    │   ├── warmup.py                # параллельная подгрузка истории
    │   └── ws_manager.py            # WebSocket connector с auto-reconnect
    ├── detectors/
    │   ├── base.py                  # Signal dataclass
    │   ├── velocity.py              # +25
    │   ├── taker_imbalance.py       # +20
    │   ├── whale_trades.py          # +20
    │   ├── volume_anomaly.py        # +15 (intra-candle)
    │   └── multi_tf_pattern.py      # +25 (Engulfing + 1h trend)
    ├── scoring/
    │   └── engine.py                # aggregate() и tiers
    ├── alerts/
    │   ├── manager.py               # cooldown, dedup, отправка
    │   ├── formatter.py             # HTML-форматтеры
    │   └── followup.py              # +5/+15/+30 min replies
    ├── notifier/
    │   └── telegram.py              # httpx async sender
    ├── storage/
    │   └── sqlite_log.py            # async SQLite logger
    └── scanner.py                   # оркестратор
```

## Тюнинг параметров

Все в `config.py`:

| Что | Default | Тюнинг |
|---|---|---|
| `TOP_N_PAIRS` | 30 | больше пар = больше сигналов, но больше нагрузки |
| `VELOCITY_PCT_THRESHOLD` | 0.5 | поднять для меньшего шума, опустить для большей чувствительности |
| `WHALE_NOTIONAL_USD` | 50_000 | для BTC/ETH можно $100k, для мелких alts $20k |
| `SCORE_MIN_TO_ALERT` | 50 | поднять до 70 если хочешь только качественные алерты |
| `ALERT_COOLDOWN_SECONDS` | 1800 | 30 мин на пару |

## Анализ accuracy через 2 недели

Все алерты пишутся в `data/signals.db`. Запросы для анализа:

```sql
-- Win rate по тирам
SELECT tier, COUNT(*) as alerts FROM alerts GROUP BY tier;

-- Топ-10 пар по количеству алертов
SELECT symbol, COUNT(*) as cnt FROM alerts GROUP BY symbol ORDER BY cnt DESC LIMIT 10;
```

Через follow-up'ы можно добавить второй analytics-проход — посмотреть, насколько пары реально росли через 5/15/30 мин после алерта.

## Roadmap

- [ ] **Phase 2:** Order Book Imbalance детектор (depth20 stream)
- [ ] **Phase 2:** Liquidation Cluster детектор (через !forceOrder с фьючей)
- [ ] **Phase 2:** RSI Divergence детектор на 15m
- [ ] **Phase 3:** Web-дашборд для просмотра signals.db и accuracy reports
- [ ] **Phase 3:** Перенос на VPS (Tokyo region для минимальной latency к Binance)

## ⚠️ Дисклеймер

Бот — **только источник информации**. Решение об открытии позиции, размере, стопе и тейке — за тобой.
Высокий score ≠ гарантированный профит. Это reduces noise, not eliminates it.
