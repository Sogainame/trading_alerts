"""
Детектор Volume Spike — резкое увеличение объёма на закрытой свече.

Логика:
  если volume[-1] > MULTIPLIER × среднее(volume[-(PERIOD+1):-1])
  → сигнал.

Это самый честный сигнал в крипте: объём не врёт. Когда он скачет в 3-5 раз
от своего среднего — на рынке что-то происходит (новость, кит, ликвидация).
Дальше уже фильтруем направлением свечи и контекстом.
"""
from typing import Optional

from config import VOLUME_AVG_PERIOD, VOLUME_SPIKE_MULTIPLIER
from src.data.candle_buffer import CandleBuffer


def detect_volume_spike(buffer: CandleBuffer, symbol: str) -> Optional[dict]:
    """
    Возвращает dict с деталями сигнала или None если сигнала нет.
    """
    candles = buffer.get(symbol)
    # Нужно минимум PERIOD+1 свечей: PERIOD на расчёт среднего + 1 текущая
    if len(candles) < VOLUME_AVG_PERIOD + 1:
        return None

    last = candles[-1]
    prev_volumes = [c.volume for c in candles[-(VOLUME_AVG_PERIOD + 1):-1]]
    avg_volume = sum(prev_volumes) / len(prev_volumes)

    if avg_volume <= 0:
        return None

    multiplier = last.volume / avg_volume
    if multiplier < VOLUME_SPIKE_MULTIPLIER:
        return None

    return {
        "pattern": "VOLUME_SPIKE",
        "direction": "BULLISH" if last.is_bullish() else "BEARISH",
        "price": last.close,
        "volume_multiplier": multiplier,
        "candle_close_time": last.close_time,
    }
