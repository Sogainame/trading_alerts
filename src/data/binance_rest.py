"""
Лёгкий клиент к Binance Spot REST API через httpx (async).
Используется только для warmup и top-pairs — горячий путь идёт через WebSocket.
"""
import logging
from typing import Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

BINANCE_REST_BASE = "https://api.binance.com"


class BinanceREST:
    def __init__(self, timeout: float = 10.0):
        self._client = httpx.AsyncClient(
            base_url=BINANCE_REST_BASE,
            timeout=timeout,
            headers={"User-Agent": "trading-alerts/2.0"},
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def get_24h_tickers(self) -> List[Dict]:
        """Все пары + статистика за 24h."""
        r = await self._client.get("/api/v3/ticker/24hr")
        r.raise_for_status()
        return r.json()

    async def get_klines(
        self, symbol: str, interval: str, limit: int = 50
    ) -> List[List]:
        """
        Получить N последних свечей. Возвращает массив массивов:
        [open_time, o, h, l, c, v, close_time, ...]
        Последняя свеча в ответе — текущая (формирующаяся), её отбрасываем при warmup.
        """
        r = await self._client.get(
            "/api/v3/klines",
            params={"symbol": symbol, "interval": interval, "limit": limit},
        )
        r.raise_for_status()
        return r.json()

    async def get_price(self, symbol: str) -> Optional[float]:
        """Текущая последняя цена. Используется в follow-up."""
        try:
            r = await self._client.get(
                "/api/v3/ticker/price", params={"symbol": symbol}
            )
            r.raise_for_status()
            return float(r.json()["price"])
        except Exception as e:
            logger.warning(f"get_price failed for {symbol}: {e}")
            return None
