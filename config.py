"""
Конфигурация сканера — все тюнящиеся параметры здесь.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# === Telegram ===
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# === Какие пары скипаем (стейблкоины и фиаты — паттерны на них бессмысленны) ===
EXCLUDE_SYMBOLS = {
    "USDCUSDT", "FDUSDUSDT", "BUSDUSDT", "TUSDUSDT", "USDPUSDT", "DAIUSDT",
    "EURUSDT", "GBPUSDT", "AUDUSDT", "JPYUSDT", "RUBUSDT", "TRYUSDT",
}

# === Сколько топ-пар по объёму мониторим ===
TOP_N_PAIRS = 30

# === Таймфрейм для MVP (расширим до 15m/1h в Phase 2) ===
TIMEFRAME = "5m"

# === Сколько свечей хранить в памяти на пару ===
# Должно быть > VOLUME_AVG_PERIOD + 2 для всех расчётов
CANDLE_BUFFER_SIZE = 50

# === Volume Spike детектор ===
# Срабатывает если текущий объём > MULTIPLIER × среднее за PERIOD предыдущих свечей
VOLUME_SPIKE_MULTIPLIER = 3.0
VOLUME_AVG_PERIOD = 20

# === Engulfing детектор ===
# Дополнительный объёмный фильтр для поглощений (паттерн без объёма = шум)
ENGULFING_VOLUME_MULTIPLIER = 1.5

# === Anti-spam ===
# Не слать алерты по одной паре чаще раза в N секунд
ALERT_COOLDOWN_SECONDS = 30 * 60  # 30 минут
