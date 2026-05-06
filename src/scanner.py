"""
Основной цикл сканера.

Что происходит:
  1. Получаем топ-N USDT пар по объёму
  2. Подгружаем последние CANDLE_BUFFER_SIZE свечей по каждой паре (warmup)
  3. Подключаемся к мультиплекс WebSocket Binance
  4. Слушаем kline-стримы. Реагируем ТОЛЬКО на закрытые свечи (k.x == True)
  5. На каждой закрытой свече прогоняем все детекторы
  6. Если паттерн прошёл фильтры (BULLISH, не cooldown) — шлём алерт
  7. После успешной отправки алерта — планируем follow-up через N минут (reply с %изменения)
"""
import asyncio
import logging
from typing import List, Optional

from binance import AsyncClient, BinanceSocketManager

from config import (
    CANDLE_BUFFER_SIZE,
    FOLLOWUP_DELAY_SECONDS,
    ONLY_BULLISH,
    TIMEFRAME,
)
from src.data.candle_buffer import Candle, CandleBuffer
from src.data.pairs import get_top_usdt_pairs
from src.filters.cooldown import CooldownFilter
from src.notifier.telegram import TelegramNotifier, format_alert, format_followup
from src.patterns.engulfing import detect_engulfing
from src.patterns.volume_spike import detect_volume_spike

logger = logging.getLogger(__name__)


class Scanner:
    def __init__(self) -> None:
        self.buffer = CandleBuffer()
        self.cooldown = CooldownFilter()
        self.notifier = TelegramNotifier()
        self.symbols: List[str] = []
        self.client: Optional[AsyncClient] = None
        # Фоновые follow-up задачи. Держим ссылки чтобы asyncio их не убил GC'ом
        self._followup_tasks: set[asyncio.Task] = set()

    async def warmup(self) -> None:
        """
        Подгрузить историческую глубину свечей для каждой пары через REST,
        чтобы детекторы сразу могли считать средние и работать с первой же закрытой свечи.
        """
        logger.info(
            f"Warming up: fetching ~{CANDLE_BUFFER_SIZE} candles for {len(self.symbols)} pairs..."
        )

        for symbol in self.symbols:
            try:
                # Берём CANDLE_BUFFER_SIZE+1, потом отрезаем последнюю (она формируется)
                klines = await self.client.get_klines(
                    symbol=symbol,
                    interval=TIMEFRAME,
                    limit=CANDLE_BUFFER_SIZE + 1,
                )
                # Последняя свеча в ответе — текущая, ещё не закрытая, отбрасываем
                candles = [Candle.from_rest(k) for k in klines[:-1]]
                self.buffer.init(symbol, candles)
            except Exception as e:
                logger.warning(f"Failed to warmup {symbol}: {e}")

        logger.info("Warmup done.")

    async def _schedule_followup(
        self, symbol: str, entry_price: float, reply_to_message_id: Optional[int]
    ) -> None:
        """
        Через FOLLOWUP_DELAY_SECONDS получаем текущую цену и шлём апдейт
        как reply на исходный алерт.

        Использует REST endpoint /api/v3/ticker/price — всегда отдаёт последнюю
        известную цену (а не цену на закрытии следующей свечи).
        """
        delay = FOLLOWUP_DELAY_SECONDS
        delay_minutes = delay // 60
        try:
            await asyncio.sleep(delay)
            ticker = await self.client.get_symbol_ticker(symbol=symbol)
            current_price = float(ticker["price"])
            msg = format_followup(symbol, entry_price, current_price, delay_minutes)
            await self.notifier.send(msg, reply_to=reply_to_message_id)
            logger.info(
                f"FOLLOW-UP SENT: {symbol} entry={entry_price:.6g} "
                f"current={current_price:.6g} "
                f"change={(current_price - entry_price) / entry_price * 100:+.2f}%"
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"Follow-up failed for {symbol}: {e}")

    def _spawn_followup(
        self, symbol: str, entry_price: float, reply_to_message_id: Optional[int]
    ) -> None:
        """
        Запустить follow-up как фоновую задачу, не блокируя основной цикл.
        Сохраняем ссылку чтобы её не собрал GC, и удаляем по завершении.
        """
        task = asyncio.create_task(
            self._schedule_followup(symbol, entry_price, reply_to_message_id)
        )
        self._followup_tasks.add(task)
        task.add_done_callback(self._followup_tasks.discard)

    async def on_candle_closed(self, symbol: str, candle: Candle) -> None:
        """
        Вызывается при закрытии каждой 5m свечи на любой из отслеживаемых пар.
        Здесь — вся торговая логика MVP.
        """
        self.buffer.add(symbol, candle)

        # Cooldown проверяем ДО детекторов — нет смысла считать если всё равно не отправим
        if not self.cooldown.can_alert(symbol):
            return

        signals: List[dict] = []

        vs = detect_volume_spike(self.buffer, symbol)
        if vs:
            signals.append(vs)

        eng = detect_engulfing(self.buffer, symbol)
        if eng:
            signals.append(eng)

        if not signals:
            return

        # Если оба сигнала, но направления разные — пропускаем (конфликт = не доверяем)
        directions = {s["direction"] for s in signals}
        if len(directions) > 1:
            logger.debug(f"{symbol}: conflicting directions, skipping")
            return

        direction = next(iter(directions))

        # Spot-only: медвежьи (BEARISH) сигналы скипаем — на споте шортить нельзя
        if ONLY_BULLISH and direction == "BEARISH":
            logger.debug(f"{symbol}: BEARISH signal skipped (ONLY_BULLISH=True)")
            return

        msg = format_alert(symbol, signals, TIMEFRAME)
        result = await self.notifier.send(msg)
        if not result:
            return

        self.cooldown.mark_alerted(symbol)
        message_id = result.get("message_id")
        logger.info(
            f"ALERT SENT: {symbol} • {' + '.join(s['pattern'] for s in signals)} "
            f"• {direction} • vol×{max(s['volume_multiplier'] for s in signals):.1f}"
        )

        # Запланировать follow-up через FOLLOWUP_DELAY_SECONDS
        self._spawn_followup(symbol, candle.close, message_id)

    async def run(self) -> None:
        self.client = await AsyncClient.create()
        try:
            self.symbols = await get_top_usdt_pairs(self.client)
            logger.info(
                f"Top {len(self.symbols)} USDT pairs: {', '.join(self.symbols[:10])}..."
            )

            await self.warmup()

            mode_str = "BULLISH only" if ONLY_BULLISH else "BULLISH + BEARISH"
            await self.notifier.send(
                f"🟢 <b>Scanner started</b>\n"
                f"Monitoring <b>{len(self.symbols)}</b> USDT pairs on <b>{TIMEFRAME}</b>\n"
                f"Mode: {mode_str}\n"
                f"Follow-up: +{FOLLOWUP_DELAY_SECONDS // 60} min after each alert"
            )

            bsm = BinanceSocketManager(self.client)
            streams = [f"{s.lower()}@kline_{TIMEFRAME}" for s in self.symbols]
            socket = bsm.multiplex_socket(streams)

            async with socket as stream:
                logger.info(
                    f"WebSocket connected ({len(streams)} streams). Listening for candle closes..."
                )
                while True:
                    msg = await stream.recv()
                    if not msg or "data" not in msg:
                        continue

                    data = msg["data"]
                    if data.get("e") != "kline":
                        continue

                    k = data["k"]
                    # k.x == True ⇔ свеча ЗАКРЫТА. Это критично — иначе будем
                    # реагировать на промежуточные тики и генерить мусорные сигналы
                    if not k.get("x"):
                        continue

                    symbol = data["s"]
                    candle = Candle.from_ws_kline(k)
                    await self.on_candle_closed(symbol, candle)

        finally:
            # Дать висящим follow-up задачам завершиться (или отменить если очень долго)
            if self._followup_tasks:
                logger.info(
                    f"Cancelling {len(self._followup_tasks)} pending follow-up tasks..."
                )
                for t in list(self._followup_tasks):
                    t.cancel()
                await asyncio.gather(*self._followup_tasks, return_exceptions=True)

            if self.client:
                await self.client.close_connection()
            await self.notifier.close()
