"""
Основной цикл сканера. Что происходит:
  1. Получаем топ-N USDT пар по объёму
  2. Подгружаем последние CANDLE_BUFFER_SIZE свечей по каждой паре (warmup)
  3. Подключаемся к мультиплекс WebSocket Binance
  4. Слушаем kline-стримы. Реагируем ТОЛЬКО на закрытые свечи (k.x == True)
  5. На каждой закрытой свече прогоняем все детекторы → если есть сигнал и не cooldown → алерт
"""
import logging
from typing import List, Optional

from binance import AsyncClient, BinanceSocketManager

from config import CANDLE_BUFFER_SIZE, TIMEFRAME
from src.data.candle_buffer import Candle, CandleBuffer
from src.data.pairs import get_top_usdt_pairs
from src.filters.cooldown import CooldownFilter
from src.notifier.telegram import TelegramNotifier, format_alert
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

        msg = format_alert(symbol, signals, TIMEFRAME)
        ok = await self.notifier.send(msg)
        if ok:
            self.cooldown.mark_alerted(symbol)
            logger.info(
                f"ALERT SENT: {symbol} • {' + '.join(s['pattern'] for s in signals)} "
                f"• {next(iter(directions))} • vol×{max(s['volume_multiplier'] for s in signals):.1f}"
            )

    async def run(self) -> None:
        self.client = await AsyncClient.create()
        try:
            self.symbols = await get_top_usdt_pairs(self.client)
            logger.info(
                f"Top {len(self.symbols)} USDT pairs: {', '.join(self.symbols[:10])}..."
            )

            await self.warmup()

            await self.notifier.send(
                f"🟢 <b>Scanner started</b>\n"
                f"Monitoring <b>{len(self.symbols)}</b> USDT pairs on <b>{TIMEFRAME}</b>"
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
            if self.client:
                await self.client.close_connection()
            await self.notifier.close()
