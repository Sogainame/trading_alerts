"""Получение топ-N USDT пар по 24h объёму."""
import logging
from typing import List

from config import EXCLUDE_SYMBOLS, TOP_N_PAIRS
from src.data.binance_rest import BinanceREST

logger = logging.getLogger(__name__)


async def get_top_usdt_pairs(rest: BinanceREST, n: int = TOP_N_PAIRS) -> List[str]:
    tickers = await rest.get_24h_tickers()
    candidates = []
    for t in tickers:
        sym = t["symbol"]
        if not sym.endswith("USDT"):
            continue
        if sym in EXCLUDE_SYMBOLS:
            continue
        try:
            qv = float(t["quoteVolume"])
        except (KeyError, ValueError):
            continue
        candidates.append((sym, qv))
    candidates.sort(key=lambda x: x[1], reverse=True)
    top = [s for s, _ in candidates[:n]]
    logger.info(f"Selected top {len(top)} USDT pairs by 24h quoteVolume")
    return top
