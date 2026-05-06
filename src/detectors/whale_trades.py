"""
Whale Trades Detector — несколько крупных market-ордеров за короткое окно.

Killer signal: один кит может быть случайностью, 3+ китовых маркет-бая за 60 сек —
это organized buying pressure, реальный сигнал.

Кит = trade с notional ≥ WHALE_NOTIONAL_USD (default $50k).
"""
from typing import Optional

from config import (
    WHALE_MIN_COUNT,
    WHALE_NOTIONAL_USD,
    WHALE_SCORE,
    WHALE_WINDOW_SECONDS,
)
from src.core.state import SymbolState
from src.detectors.base import Signal


def detect_whale_trades(state: SymbolState) -> Optional[Signal]:
    if not state.trades:
        return None

    now_ms = state.trades[-1].timestamp
    window_start_ms = now_ms - WHALE_WINDOW_SECONDS * 1000

    whale_buys = 0
    whale_sells = 0
    buy_total = 0.0
    sell_total = 0.0

    for t in state.trades:
        if t.timestamp < window_start_ms:
            continue
        if t.notional < WHALE_NOTIONAL_USD:
            continue
        if t.is_market_buy:
            whale_buys += 1
            buy_total += t.notional
        else:
            whale_sells += 1
            sell_total += t.notional

    if whale_buys >= WHALE_MIN_COUNT and whale_buys > whale_sells:
        return Signal(
            detector_name="WHALE_BUYS",
            direction="BULLISH",
            score_contribution=WHALE_SCORE,
            description=f"{whale_buys} whale buys ≥${WHALE_NOTIONAL_USD//1000}k за {WHALE_WINDOW_SECONDS}s (${buy_total/1000:.0f}k)",
            extra={"count": whale_buys, "total_usd": buy_total},
        )

    if whale_sells >= WHALE_MIN_COUNT and whale_sells > whale_buys:
        return Signal(
            detector_name="WHALE_SELLS",
            direction="BEARISH",
            score_contribution=WHALE_SCORE,
            description=f"{whale_sells} whale sells ≥${WHALE_NOTIONAL_USD//1000}k за {WHALE_WINDOW_SECONDS}s (${sell_total/1000:.0f}k)",
            extra={"count": whale_sells, "total_usd": sell_total},
        )

    return None
