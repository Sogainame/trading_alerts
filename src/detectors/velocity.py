"""
Velocity Detector — цена изменилась на X% за окно N секунд.

Самый честный сигнал импульса в realtime. Считается по trades буферу,
не по свечам — нет лагов от закрытия свечи.
"""
from typing import Optional

from config import VELOCITY_PCT_THRESHOLD, VELOCITY_SCORE, VELOCITY_WINDOW_SECONDS
from src.core.state import SymbolState
from src.detectors.base import Signal


def detect_velocity(state: SymbolState) -> Optional[Signal]:
    if len(state.trades) < 2:
        return None

    now_ms = state.trades[-1].timestamp
    window_start_ms = now_ms - VELOCITY_WINDOW_SECONDS * 1000

    # Найти первый trade в окне (deque отсортирован по времени)
    start_price = None
    for t in state.trades:
        if t.timestamp >= window_start_ms:
            start_price = t.price
            break
    if start_price is None or start_price <= 0:
        return None

    end_price = state.trades[-1].price
    pct_change = (end_price - start_price) / start_price * 100

    if abs(pct_change) < VELOCITY_PCT_THRESHOLD:
        return None

    direction = "BULLISH" if pct_change > 0 else "BEARISH"
    return Signal(
        detector_name="VELOCITY",
        direction=direction,
        score_contribution=VELOCITY_SCORE,
        description=f"{pct_change:+.2f}% за {VELOCITY_WINDOW_SECONDS}s",
        extra={"pct_change": pct_change, "window_s": VELOCITY_WINDOW_SECONDS},
    )
