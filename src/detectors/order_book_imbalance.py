"""
Order Book Imbalance Detector.

Сравнивает суммарный объём bids vs asks в первых N уровнях.
Если ratio > THRESHOLD — давление в одну сторону (больше денег ждёт купить чем продать).
"""
from typing import Optional

from config import OBI_RATIO_THRESHOLD, OBI_SCORE, OBI_TOP_LEVELS
from src.core.state import SymbolState
from src.detectors.base import Signal


def detect_order_book_imbalance(state: SymbolState) -> Optional[Signal]:
    ob = state.order_book
    if not ob.bids or not ob.asks:
        return None

    bid_notional = sum(p * q for p, q in ob.bids[:OBI_TOP_LEVELS])
    ask_notional = sum(p * q for p, q in ob.asks[:OBI_TOP_LEVELS])

    if bid_notional <= 0 or ask_notional <= 0:
        return None

    if bid_notional / ask_notional >= OBI_RATIO_THRESHOLD:
        ratio = bid_notional / ask_notional
        return Signal(
            detector_name="ORDER_BOOK_IMBALANCE",
            direction="BULLISH",
            score_contribution=OBI_SCORE,
            description=f"Bid/Ask ratio {ratio:.1f} (давление вверх)",
            extra={"ratio": ratio, "bid_usd": bid_notional, "ask_usd": ask_notional},
        )

    if ask_notional / bid_notional >= OBI_RATIO_THRESHOLD:
        ratio = ask_notional / bid_notional
        return Signal(
            detector_name="ORDER_BOOK_IMBALANCE",
            direction="BEARISH",
            score_contribution=OBI_SCORE,
            description=f"Ask/Bid ratio {ratio:.1f} (давление вниз)",
            extra={"ratio": ratio, "bid_usd": bid_notional, "ask_usd": ask_notional},
        )

    return None
