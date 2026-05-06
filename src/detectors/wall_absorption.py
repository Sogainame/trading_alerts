"""
Wall Absorption Detector — самый сильный сигнал из стакана.

Логика: была крупная ask-стена сверху, цена в неё уперлась, и стена ИСЧЕЗЛА
(была съедена маркет-байами или просто отменена). Это означает что путь наверх
освободился — крупный продавец вышел.

handler.py трекает это через recent_absorptions. Здесь мы просто читаем
свежие события из этой очереди.

Симметрично работает для медвежьих случаев: bid-стена снизу была съедена =
дно пробито = путь вниз свободен.
"""
import time
from typing import Optional

from config import (
    ABSORPTION_LOOKBACK_SECONDS,
    ABSORPTION_MIN_INITIAL_USD,
    ABSORPTION_SCORE,
)
from src.core.state import SymbolState
from src.detectors.base import Signal


def detect_wall_absorption(state: SymbolState) -> Optional[Signal]:
    ob = state.order_book
    if not ob.recent_absorptions:
        return None

    now = time.time()
    cutoff = now - ABSORPTION_LOOKBACK_SECONDS

    # Берём только свежие events
    fresh = [a for a in ob.recent_absorptions if a[0] >= cutoff]
    if not fresh:
        return None

    # Ищем самое крупное событие
    biggest = max(fresh, key=lambda x: x[3])
    ts, side, price, initial_notional = biggest

    if initial_notional < ABSORPTION_MIN_INITIAL_USD:
        return None

    age = now - ts

    if side == "ask":
        # Ask-стена сверху съедена = bullish (путь наверх свободен)
        return Signal(
            detector_name="WALL_ABSORPTION",
            direction="BULLISH",
            score_contribution=ABSORPTION_SCORE,
            description=(
                f"💥 Поглощена ask-стена ${initial_notional/1000:.0f}k "
                f"на {price:.6g} ({int(age)}s назад)"
            ),
            extra={"side": side, "price": price, "initial_usd": initial_notional, "age_s": int(age)},
        )
    else:
        # Bid-стена снизу съедена = bearish (поддержка пробита)
        return Signal(
            detector_name="WALL_ABSORPTION",
            direction="BEARISH",
            score_contribution=ABSORPTION_SCORE,
            description=(
                f"💥 Пробита bid-стена ${initial_notional/1000:.0f}k "
                f"на {price:.6g} ({int(age)}s назад)"
            ),
            extra={"side": side, "price": price, "initial_usd": initial_notional, "age_s": int(age)},
        )
