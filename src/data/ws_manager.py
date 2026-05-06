"""
WebSocket connector к Binance combined streams.

Скоростные оптимизации:
  - ОДНО TCP соединение на все потоки (multiplex)
  - compression=None (не тратим CPU на gzip)
  - max_size большой (16MB) чтобы Binance не отклонил большой message
  - Реконнект с exp backoff
"""
import asyncio
import json
import logging
from typing import Awaitable, Callable, List

import websockets
from websockets.exceptions import ConnectionClosed

logger = logging.getLogger(__name__)

BINANCE_WS_BASE = "wss://stream.binance.com:9443/stream?streams="

# Binance hard limit — 1024 потоков на одном WS connection
MAX_STREAMS_PER_CONNECTION = 1024


class WebSocketManager:
    def __init__(
        self,
        streams: List[str],
        on_message: Callable[[dict], Awaitable[None]],
    ):
        if len(streams) > MAX_STREAMS_PER_CONNECTION:
            raise ValueError(
                f"Too many streams: {len(streams)} > {MAX_STREAMS_PER_CONNECTION}. "
                "Need to split across multiple connections (not implemented)."
            )
        if not streams:
            raise ValueError("Streams list is empty")
        self._streams = streams
        self._on_message = on_message
        self._url = BINANCE_WS_BASE + "/".join(streams)

    async def run_forever(self) -> None:
        backoff = 1
        while True:
            try:
                logger.info(
                    f"Connecting to Binance WS ({len(self._streams)} streams)..."
                )
                async with websockets.connect(
                    self._url,
                    ping_interval=20,    # Binance closes idle conn after ~30 min
                    ping_timeout=10,
                    max_size=2**24,       # 16MB
                    compression=None,     # raw speed
                    open_timeout=15,
                    close_timeout=5,
                ) as ws:
                    logger.info("WS connected")
                    backoff = 1
                    async for raw in ws:
                        try:
                            msg = json.loads(raw)
                        except json.JSONDecodeError:
                            logger.warning("Bad JSON in WS message, skipping")
                            continue
                        try:
                            await self._on_message(msg)
                        except Exception:
                            # Никогда не роняем connection из-за ошибки в обработчике
                            logger.exception("Error in on_message handler")
            except ConnectionClosed as e:
                logger.warning(f"WS closed (code={e.code} reason={e.reason}). Reconnect in {backoff}s")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)
            except (OSError, asyncio.TimeoutError) as e:
                logger.warning(f"WS network error: {e}. Reconnect in {backoff}s")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)
            except Exception as e:
                logger.exception(f"WS unexpected error: {e}. Reconnect in {backoff}s")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)
