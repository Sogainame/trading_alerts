"""
Static Wall Detector.

Ищет крупные ордера которые сидят в стакане ≥STATIC_WALL_MIN_LIFETIME_SECONDS.
Это anti-spoof фильтр: спуферы ставят-снимают за <10 секунд, реальные стены
держатся дольше.

Сигнал генерится так:
  - Если есть мощный bid wall снизу + цена выше него → BULLISH (есть защита снизу)
  - Если есть мощный ask wall сверху + цена ниже него → потенциальный target
    (но не bearish сам по себе — он может быть absorbed)

Этот детектор СОПУТСТВУЮЩИЙ — он не главный сигнал, он усиливает уже найденный
другими детекторами.
"""
import time
from typing import Optional

from config import STATIC_WALL_MIN_LIFETIME_SECONDS, STATIC_WALL_SCORE
from src.core.state import SymbolState
from src.detectors.base import Signal


def detect_static_wall_support(state: SymbolState) -> Optional[Signal]:
    """
    Ищем большой bid wall в стакане который существует достаточно долго.
    Если он есть и цена выше него — BULLISH сигнал (поддержка реальная).
    """
    ob = state.order_book
    if not ob.bids:
        return None

    best_bid = ob.best_bid
    if best_bid is None:
        return None

    now = time.time()

    # Ищем самую крупную статическую стену среди bid'ов
    best_wall = None
    best_wall_size = 0.0
    for (side, price), event in ob.level_history.items():
        if side != "bid":
            continue
        if price > best_bid:
            continue  # этот уровень уже не валиден (цена ниже него)
        lifetime = now - event.first_seen_ts
        if lifetime < STATIC_WALL_MIN_LIFETIME_SECONDS:
            continue
        if event.notional > best_wall_size:
            best_wall_size = event.notional
            best_wall = event

    if best_wall is None:
        return None

    lifetime = now - best_wall.first_seen_ts
    distance_pct = (best_bid - best_wall.price) / best_bid * 100

    return Signal(
        detector_name="STATIC_WALL_SUPPORT",
        direction="BULLISH",
        score_contribution=STATIC_WALL_SCORE,
        description=(
            f"Поддержка ${best_wall.notional/1000:.0f}k на {best_wall.price:.6g} "
            f"(−{distance_pct:.2f}%, живёт {int(lifetime)}s)"
        ),
        extra={
            "wall_price": best_wall.price,
            "wall_notional": best_wall.notional,
            "lifetime_s": int(lifetime),
            "distance_pct": distance_pct,
        },
    )
