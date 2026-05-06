"""
FollowupScheduler — отложенные проверки цены через несколько интервалов после алерта.

Каждый алерт получает 3 follow-up'а: +5min, +15min, +30min — ответами (reply)
на исходное сообщение. Это даёт возможность через 2 недели проанализировать
точность сигналов на разных горизонтах.
"""
import asyncio
import logging
from typing import Optional, Set

from src.alerts.formatter import format_followup
from src.data.binance_rest import BinanceREST
from src.notifier.telegram import TelegramNotifier

logger = logging.getLogger(__name__)


class FollowupScheduler:
    def __init__(self, notifier: TelegramNotifier, rest: BinanceREST):
        self.notifier = notifier
        self.rest = rest
        self._tasks: Set[asyncio.Task] = set()

    def schedule(
        self,
        symbol: str,
        entry_price: float,
        delay_seconds: int,
        reply_to_message_id: Optional[int],
    ) -> None:
        task = asyncio.create_task(
            self._run(symbol, entry_price, delay_seconds, reply_to_message_id)
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run(
        self,
        symbol: str,
        entry_price: float,
        delay_seconds: int,
        reply_to_message_id: Optional[int],
    ) -> None:
        delay_min = delay_seconds // 60
        try:
            await asyncio.sleep(delay_seconds)
            current = await self.rest.get_price(symbol)
            if current is None:
                return
            msg = format_followup(symbol, entry_price, current, delay_min)
            await self.notifier.send(msg, reply_to=reply_to_message_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(f"Follow-up failed for {symbol} +{delay_min}m")

    async def shutdown(self) -> None:
        if not self._tasks:
            return
        for t in list(self._tasks):
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
