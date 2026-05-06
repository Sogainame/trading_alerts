"""
Warmup: подгрузить историческую глубину свечей для всех пар по всем таймфреймам.
Делаем параллельно через asyncio.gather для скорости старта.
"""
import asyncio
import logging
from typing import List

from src.core.state import Candle, GlobalState
from src.data.binance_rest import BinanceREST

logger = logging.getLogger(__name__)


# Сколько свечей подгружаем для каждого ТФ — должно покрывать длиннейший индикатор
WARMUP_LIMITS = {
    "5m": 51,    # для VOLUME_AVG_PERIOD=20 + buffer
    "15m": 31,
    "1h": 51,    # для EMA50 на 1h
}


async def _warmup_one(
    rest: BinanceREST, symbol: str, interval: str, state: GlobalState
) -> None:
    limit = WARMUP_LIMITS.get(interval, 50)
    try:
        klines = await rest.get_klines(symbol, interval, limit=limit)
        # Последняя свеча — формирующаяся, отрезаем
        candles = [Candle.from_rest(k) for k in klines[:-1]]
        st = state.get_or_create(symbol)
        if interval == "5m":
            st.candles_5m.extend(candles)
        elif interval == "15m":
            st.candles_15m.extend(candles)
        elif interval == "1h":
            st.candles_1h.extend(candles)
    except Exception as e:
        logger.warning(f"Warmup failed for {symbol} {interval}: {e}")


async def warmup_all(
    rest: BinanceREST,
    symbols: List[str],
    intervals: List[str],
    state: GlobalState,
    concurrency: int = 8,
) -> None:
    """
    Параллельный warmup с ограничением concurrency, чтобы не словить rate limit.
    Binance: 1200 req/min weight. Каждый /klines вызов = weight 1. У нас 30×3 = 90 запросов — безопасно.
    """
    sem = asyncio.Semaphore(concurrency)

    async def bounded(sym: str, interval: str) -> None:
        async with sem:
            await _warmup_one(rest, sym, interval, state)

    tasks = [bounded(s, iv) for s in symbols for iv in intervals]
    logger.info(f"Warmup: {len(tasks)} REST calls in parallel (concurrency={concurrency})...")
    await asyncio.gather(*tasks)
    logger.info("Warmup done.")
