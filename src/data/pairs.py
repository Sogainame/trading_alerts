"""Получение топ-N USDT пар по 24h объёму со спота Binance."""
import logging

from binance import AsyncClient

from config import EXCLUDE_SYMBOLS, TOP_N_PAIRS

logger = logging.getLogger(__name__)


async def get_top_usdt_pairs(client: AsyncClient, n: int = TOP_N_PAIRS) -> list[str]:
    """
    Возвращает список из N самых ликвидных USDT-пар на споте Binance,
    отсортированных по убыванию quote volume (объём в USDT за 24 часа).
    """
    tickers = await client.get_ticker()  # 24h stats для всех пар

    usdt_pairs: list[tuple[str, float]] = []
    for t in tickers:
        symbol = t["symbol"]
        if not symbol.endswith("USDT"):
            continue
        if symbol in EXCLUDE_SYMBOLS:
            continue
        # quoteVolume = объём в USDT (количество * цена)
        try:
            quote_volume = float(t["quoteVolume"])
        except (KeyError, ValueError):
            continue
        usdt_pairs.append((symbol, quote_volume))

    usdt_pairs.sort(key=lambda x: x[1], reverse=True)
    top = [symbol for symbol, _ in usdt_pairs[:n]]

    logger.info(f"Selected top {len(top)} USDT pairs by 24h volume")
    return top
