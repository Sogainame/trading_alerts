"""
Taker Imbalance Detector — соотношение market buys vs market sells по объёму
за окно N секунд.

market buy = taker_is_buyer = is_buyer_maker == False
Если 70%+ объёма ушло в market buys — агрессивные покупатели → bullish.

В отличие от классических индикаторов это РЕАЛЬНОЕ движение бабла
(люди реально покупают сейчас), а не геометрия графика.
"""
from typing import Optional

from config import (
    TAKER_IMBALANCE_MIN_TRADES,
    TAKER_IMBALANCE_SCORE,
    TAKER_IMBALANCE_THRESHOLD,
    TAKER_IMBALANCE_WINDOW_SECONDS,
)
from src.core.state import SymbolState
from src.detectors.base import Signal


def detect_taker_imbalance(state: SymbolState) -> Optional[Signal]:
    if len(state.trades) < TAKER_IMBALANCE_MIN_TRADES:
        return None

    now_ms = state.trades[-1].timestamp
    window_start_ms = now_ms - TAKER_IMBALANCE_WINDOW_SECONDS * 1000

    buy_vol = 0.0
    sell_vol = 0.0
    count = 0

    # Идём с конца назад до окна — для скорости (но deque не O(1) на reversed iter,
    # на 500 элементов это микросекунды, неважно)
    for t in state.trades:
        if t.timestamp < window_start_ms:
            continue
        count += 1
        if t.is_market_buy:
            buy_vol += t.notional
        else:
            sell_vol += t.notional

    if count < TAKER_IMBALANCE_MIN_TRADES:
        return None

    total = buy_vol + sell_vol
    if total <= 0:
        return None

    buy_ratio = buy_vol / total

    if buy_ratio >= TAKER_IMBALANCE_THRESHOLD:
        return Signal(
            detector_name="TAKER_IMBALANCE",
            direction="BULLISH",
            score_contribution=TAKER_IMBALANCE_SCORE,
            description=f"Takers: {buy_ratio*100:.0f}% buys ({TAKER_IMBALANCE_WINDOW_SECONDS}s)",
            extra={"buy_ratio": buy_ratio, "count": count},
        )

    if (1 - buy_ratio) >= TAKER_IMBALANCE_THRESHOLD:
        return Signal(
            detector_name="TAKER_IMBALANCE",
            direction="BEARISH",
            score_contribution=TAKER_IMBALANCE_SCORE,
            description=f"Takers: {(1-buy_ratio)*100:.0f}% sells ({TAKER_IMBALANCE_WINDOW_SECONDS}s)",
            extra={"buy_ratio": buy_ratio, "count": count},
        )

    return None
