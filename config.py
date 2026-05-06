"""
Конфигурация Trading Alerts v2.

Все веса, пороги, окна — здесь. Тюним по факту работы (после 2 недель в SQLite-логе).
"""
import os
from dotenv import load_dotenv

load_dotenv()

# === Telegram ===
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# === Какие пары НЕ сканируем (стейблкоины и фиаты) ===
EXCLUDE_SYMBOLS = {
    "USDCUSDT", "FDUSDUSDT", "BUSDUSDT", "TUSDUSDT", "USDPUSDT", "DAIUSDT",
    "EURUSDT", "GBPUSDT", "AUDUSDT", "JPYUSDT", "RUBUSDT", "TRYUSDT", "USD1USDT",
}

# === Сколько топ-пар сканируем (по 24h объёму USDT на споте) ===
TOP_N_PAIRS = 30

# === Таймфреймы (свечные стримы) ===
TIMEFRAMES = ("5m", "15m", "1h")

# === Spot-only ===
ONLY_BULLISH = True

# === Cooldown ===
ALERT_COOLDOWN_SECONDS = 30 * 60  # 30 мин на пару

# === Follow-ups: replies на алерт через эти интервалы ===
FOLLOWUP_DELAYS_SECONDS = (5 * 60, 15 * 60, 30 * 60)

# === Scoring tiers ===
TIER_WATCH = 50
TIER_STRONG = 70
TIER_PREMIUM = 85
SCORE_MIN_TO_ALERT = 50  # ниже этого — не шлём

# ───────────────────────────────────────────────────────────────────────
# DETECTORS — у каждого свой score_contribution и параметры
# ───────────────────────────────────────────────────────────────────────

# === 1. Velocity: цена изменилась на ≥X% за окно ===
VELOCITY_WINDOW_SECONDS = 30
VELOCITY_PCT_THRESHOLD = 0.5  # %
VELOCITY_SCORE = 25

# === 2. Taker Imbalance: market buys >> market sells по объёму ===
TAKER_IMBALANCE_WINDOW_SECONDS = 60
TAKER_IMBALANCE_THRESHOLD = 0.70  # 70% объёма должно быть в одну сторону
TAKER_IMBALANCE_MIN_TRADES = 20    # минимум сделок в окне
TAKER_IMBALANCE_SCORE = 20

# === 3. Whale Trades: крупные market-ордеры ===
WHALE_NOTIONAL_USD = 50_000        # одна сделка ≥ $50k
WHALE_WINDOW_SECONDS = 60
WHALE_MIN_COUNT = 3
WHALE_SCORE = 20

# === 4. Volume Anomaly (intra-candle, без ожидания закрытия!) ===
# Текущая формирующаяся 5m свеча уже накопила больше объёма чем обычно
VOLUME_ANOMALY_MULTIPLIER = 2.0
VOLUME_ANOMALY_AVG_PERIOD = 20
VOLUME_ANOMALY_SCORE = 15

# === 5. Multi-TF Pattern: Engulfing + Volume + 1h тренд (на закрытии 5m) ===
MULTI_TF_VOLUME_MULT = 1.5
MULTI_TF_VOLUME_PERIOD = 20
MULTI_TF_TREND_EMA = 50  # EMA50 на 1h как фильтр тренда
MULTI_TF_SCORE = 25

# ───────────────────────────────────────────────────────────────────────
# ORDER BOOK LAYER (Phase 2A) — детекторы стакана
# ───────────────────────────────────────────────────────────────────────

# === 6. Static Wall: крупный ордер сидит ≥N секунд ===
# Спуферы ставят-снимают за <10s. Реальные стены живут дольше.
STATIC_WALL_MIN_LIFETIME_SECONDS = 30
STATIC_WALL_MIN_USD = 100_000           # минимальный размер стены чтобы её считать
STATIC_WALL_TOP_LEVELS = 20             # смотрим только в первых 20 уровнях
STATIC_WALL_SCORE = 15                  # балл если есть подтверждающая стена снизу/сверху

# === 7. Order Book Imbalance: давление сверху или снизу ===
OBI_TOP_LEVELS = 20                     # сравниваем суммы первых 20 bids vs asks
OBI_RATIO_THRESHOLD = 1.8               # bids:asks ≥1.8 = bullish, asks:bids ≥1.8 = bearish
OBI_SCORE = 15

# === 8. Wall Absorption: стена была → цена дошла → стена исчезла (съедена) ===
ABSORPTION_MIN_INITIAL_USD = 200_000    # стена должна быть существенной чтобы считалось
ABSORPTION_REMNANT_PCT = 0.20           # осталось ≤20% от изначального размера
ABSORPTION_LOOKBACK_SECONDS = 60        # ищем absorption события за последнюю минуту
ABSORPTION_SCORE = 25                   # это сильнейший сигнал направления

# === Targets calculation (стоп / цель) ===
# Ищем ближайшие крупные стены — bid снизу = стоп, ask сверху = цель
TARGET_MIN_WALL_USD = 100_000           # порог чтобы уровень считался "ориентиром"
TARGET_MAX_DISTANCE_PCT = 3.0           # ищем стены не дальше 3% от текущей цены

# === SQLite ===
DB_PATH = "data/signals.db"
