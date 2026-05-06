"""
Volume Anomaly Detector — текущая (незакрытая) 5m свеча уже накопила
больше объёма чем средний за последние N закрытых свечей.

Это решает фундаментальную проблему: алерт ловится В МОМЕНТЕ движения,
а не на закрытии 5m свечи (через 5 минут после события).

Анти-спам: для одной open_time свечи алертим только один раз, чтобы тики
не триггерили нас 100 раз внутри одной свечи.
"""
from typing import Optional

from config import (
    VOLUME_ANOMALY_AVG_PERIOD,
    VOLUME_ANOMALY_MULTIPLIER,
    VOLUME_ANOMALY_SCORE,
)
from src.core.state import SymbolState
from src.detectors.base import Signal


def detect_volume_anomaly(state: SymbolState) -> Optional[Signal]:
    current = state.current_5m
    if current is None:
        return None

    closed = state.candles_5m
    if len(closed) < VOLUME_ANOMALY_AVG_PERIOD:
        return None

    # Анти-спам внутри одной свечи
    if state.last_volume_anomaly_at == current.open_time:
        return None

    avg_vol = (
        sum(c.volume for c in list(closed)[-VOLUME_ANOMALY_AVG_PERIOD:])
        / VOLUME_ANOMALY_AVG_PERIOD
    )
    if avg_vol <= 0:
        return None

    multiplier = current.volume / avg_vol
    if multiplier < VOLUME_ANOMALY_MULTIPLIER:
        return None

    direction = "BULLISH" if current.close >= current.open else "BEARISH"

    return Signal(
        detector_name="VOLUME_ANOMALY",
        direction=direction,
        score_contribution=VOLUME_ANOMALY_SCORE,
        description=f"Vol {multiplier:.1f}x avg (intra-5m, ещё не закрылась)",
        extra={"multiplier": multiplier, "open_time": current.open_time},
    )


def mark_volume_anomaly_alerted(state: SymbolState) -> None:
    """Пометить что для текущей свечи мы уже алертили (вызывается из AlertManager)."""
    if state.current_5m is not None:
        state.last_volume_anomaly_at = state.current_5m.open_time
