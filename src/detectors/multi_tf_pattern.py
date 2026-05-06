"""
Multi-TF Pattern Detector — самый сильный pattern-сигнал.

Логика:
  1. Engulfing на 5m (TA-Lib CDLENGULFING)
  2. Объём этой свечи > MULT × среднее за период
  3. EMA50 на 1h в правильную сторону (uptrend для bullish engulfing, downtrend для bearish)

Без всех трёх условий — None. Этот детектор стреляет редко, но качественно.
Запускается ТОЛЬКО при закрытии 5m свечи.
"""
from typing import Optional

import numpy as np
import talib

from config import (
    MULTI_TF_SCORE,
    MULTI_TF_TREND_EMA,
    MULTI_TF_VOLUME_MULT,
    MULTI_TF_VOLUME_PERIOD,
)
from src.core.state import SymbolState
from src.detectors.base import Signal


def detect_multi_tf_pattern(state: SymbolState) -> Optional[Signal]:
    candles_5m = list(state.candles_5m)
    if len(candles_5m) < MULTI_TF_VOLUME_PERIOD + 2:
        return None
    if len(state.candles_1h) < MULTI_TF_TREND_EMA + 2:
        return None

    # 1. Engulfing на 5m
    o = np.array([c.open for c in candles_5m], dtype=np.float64)
    h = np.array([c.high for c in candles_5m], dtype=np.float64)
    l = np.array([c.low for c in candles_5m], dtype=np.float64)
    c = np.array([c.close for c in candles_5m], dtype=np.float64)

    eng = talib.CDLENGULFING(o, h, l, c)
    if eng[-1] == 0:
        return None

    # 2. Объём
    last = candles_5m[-1]
    prev_vols = [x.volume for x in candles_5m[-(MULTI_TF_VOLUME_PERIOD + 1):-1]]
    avg_vol = sum(prev_vols) / len(prev_vols)
    if avg_vol <= 0:
        return None
    vol_mult = last.volume / avg_vol
    if vol_mult < MULTI_TF_VOLUME_MULT:
        return None

    # 3. Тренд на 1h
    h1_closes = np.array([c.close for c in state.candles_1h], dtype=np.float64)
    ema = talib.EMA(h1_closes, timeperiod=MULTI_TF_TREND_EMA)
    if np.isnan(ema[-1]) or np.isnan(ema[-2]):
        return None

    last_close_1h = h1_closes[-1]
    h1_uptrend = (ema[-1] > ema[-2]) and (last_close_1h > ema[-1])
    h1_downtrend = (ema[-1] < ema[-2]) and (last_close_1h < ema[-1])

    direction = "BULLISH" if eng[-1] > 0 else "BEARISH"

    if direction == "BULLISH" and not h1_uptrend:
        return None
    if direction == "BEARISH" and not h1_downtrend:
        return None

    return Signal(
        detector_name="MULTI_TF_PATTERN",
        direction=direction,
        score_contribution=MULTI_TF_SCORE,
        description=f"Engulfing 5m + vol {vol_mult:.1f}x + 1h trend",
        extra={"vol_mult": vol_mult},
    )
