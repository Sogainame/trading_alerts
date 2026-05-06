"""
Детектор Bullish/Bearish Engulfing с обязательным подтверждением объёмом.

Engulfing = текущая свеча "поглощает" телом предыдущую противоположного цвета:
  - Bullish: вчера красная, сегодня зелёная и тело больше вчерашнего
  - Bearish: вчера зелёная, сегодня красная и тело больше вчерашнего

ВАЖНО: голый engulfing без объёма = шум. Нужно подтверждение объёмом
(полтора-два средних минимум), иначе ложных сигналов на низких ТФ — лавина.

TA-Lib делает геометрию за нас (CDLENGULFING), мы добавляем объёмный фильтр.
"""
from typing import Optional

import talib

from config import ENGULFING_VOLUME_MULTIPLIER, VOLUME_AVG_PERIOD
from src.data.candle_buffer import CandleBuffer


def detect_engulfing(buffer: CandleBuffer, symbol: str) -> Optional[dict]:
    """
    Возвращает сигнал, если на последней закрытой свече TA-Lib нашёл engulfing
    И объём этой свечи > ENGULFING_VOLUME_MULTIPLIER × среднего за VOLUME_AVG_PERIOD.
    """
    candles = buffer.get(symbol)
    # Нужно минимум 2 свечи для engulfing + PERIOD для среднего объёма
    if len(candles) < VOLUME_AVG_PERIOD + 2:
        return None

    arrays = buffer.to_arrays(symbol)

    # TA-Lib: +100 = bullish engulfing, -100 = bearish, 0 = ничего нет
    engulfing = talib.CDLENGULFING(
        arrays["open"],
        arrays["high"],
        arrays["low"],
        arrays["close"],
    )

    last_signal = engulfing[-1]
    if last_signal == 0:
        return None

    last = candles[-1]
    prev_volumes = [c.volume for c in candles[-(VOLUME_AVG_PERIOD + 1):-1]]
    avg_volume = sum(prev_volumes) / len(prev_volumes)

    if avg_volume <= 0:
        return None

    multiplier = last.volume / avg_volume
    if multiplier < ENGULFING_VOLUME_MULTIPLIER:
        return None

    return {
        "pattern": "ENGULFING",
        "direction": "BULLISH" if last_signal > 0 else "BEARISH",
        "price": last.close,
        "volume_multiplier": multiplier,
        "candle_close_time": last.close_time,
    }
