"""
Scanner v2.1 — главный оркестратор с Order Book Layer.

Hot path:
  WS message → parse by event type → update state → run detectors → score → maybe_alert

Подписки:
  - <symbol>@aggTrade   — каждая сделка (для velocity, taker imbalance, whale)
  - <symbol>@kline_5m   — 5-минутные свечи (intra-candle volume + post-close pattern)
  - <symbol>@kline_15m  — для будущих TF-confirmation детекторов
  - <symbol>@kline_1h   — для multi-TF pattern (EMA50 trend filter)
  - <symbol>@depth20@100ms — стакан 20 уровней раз в 100ms

Total streams = 30 пар × 5 = 150. Хорошо в пределах limit'а 1024 на одно WS-соединение.
"""
import logging
from typing import List

from config import TIMEFRAMES
from src.alerts.followup import FollowupScheduler
from src.alerts.manager import AlertManager
from src.core.state import Candle, GlobalState, SymbolState, Trade
from src.data.binance_rest import BinanceREST
from src.data.order_book_handler import handle_depth_message
from src.data.pairs import get_top_usdt_pairs
from src.data.warmup import warmup_all
from src.data.ws_manager import WebSocketManager
from src.detectors.multi_tf_pattern import detect_multi_tf_pattern
from src.detectors.order_book_imbalance import detect_order_book_imbalance
from src.detectors.static_wall import detect_static_wall_support
from src.detectors.taker_imbalance import detect_taker_imbalance
from src.detectors.velocity import detect_velocity
from src.detectors.volume_anomaly import detect_volume_anomaly
from src.detectors.wall_absorption import detect_wall_absorption
from src.detectors.whale_trades import detect_whale_trades
from src.notifier.telegram import TelegramNotifier
from src.scoring.engine import aggregate
from src.storage.sqlite_log import SignalLogger

logger = logging.getLogger(__name__)


class Scanner:
    def __init__(self) -> None:
        self.state = GlobalState()
        self.rest = BinanceREST()
        self.notifier = TelegramNotifier()
        self.signal_logger = SignalLogger()
        self.followup = FollowupScheduler(self.notifier, self.rest)
        self.alert_manager = AlertManager(
            self.notifier, self.followup, self.signal_logger
        )
        self.symbols: List[str] = []

    # ─────────────────────────────────────────────────────────────────
    # Hot path: WS message handler
    # ─────────────────────────────────────────────────────────────────

    async def handle_ws_message(self, msg: dict) -> None:
        # Combined-stream формат: {"stream": "...", "data": {...}}
        data = msg.get("data")
        if not data:
            return

        stream = msg.get("stream", "")

        # depth20 не имеет поля "e" в сообщении — определяем по имени стрима
        if "@depth20" in stream:
            symbol = stream.split("@")[0].upper()
            st = self.state.get_or_create(symbol)
            handle_depth_message(st, data)
            return

        event = data.get("e")
        symbol = data.get("s")
        if not symbol:
            return
        st = self.state.get_or_create(symbol)

        if event == "aggTrade":
            await self._on_trade(st, data)
        elif event == "kline":
            await self._on_kline(st, data)

    async def _on_trade(self, state: SymbolState, data: dict) -> None:
        trade = Trade(
            timestamp=data["T"],
            price=float(data["p"]),
            quantity=float(data["q"]),
            is_buyer_maker=data["m"],
        )
        state.trades.append(trade)

        # Trade-driven + order-book-driven детекторы
        signals = []
        for detector in (
            detect_velocity,
            detect_taker_imbalance,
            detect_whale_trades,
            detect_volume_anomaly,
            detect_order_book_imbalance,
            detect_static_wall_support,
            detect_wall_absorption,
        ):
            sig = detector(state)
            if sig:
                signals.append(sig)

        if not signals:
            return

        result = aggregate(signals)
        await self.alert_manager.maybe_alert(state, result, trade.price)

    async def _on_kline(self, state: SymbolState, data: dict) -> None:
        k = data["k"]
        interval = k["i"]
        is_closed = bool(k.get("x", False))
        candle = Candle.from_ws_kline(k, is_closed=is_closed)

        if interval == "5m":
            if is_closed:
                state.candles_5m.append(candle)
                state.current_5m = None
                # На закрытии 5m — запускаем pattern детектор
                pattern_sig = detect_multi_tf_pattern(state)
                if pattern_sig is not None:
                    # Combine с активными confirming сигналами в ту же сторону
                    extra = []
                    for det in (
                        detect_velocity,
                        detect_taker_imbalance,
                        detect_whale_trades,
                        detect_order_book_imbalance,
                        detect_static_wall_support,
                        detect_wall_absorption,
                    ):
                        s = det(state)
                        if s and s.direction == pattern_sig.direction:
                            extra.append(s)
                    result = aggregate([pattern_sig] + extra)
                    await self.alert_manager.maybe_alert(state, result, candle.close)
            else:
                state.current_5m = candle
        elif interval == "15m":
            if is_closed:
                state.candles_15m.append(candle)
        elif interval == "1h":
            if is_closed:
                state.candles_1h.append(candle)

    # ─────────────────────────────────────────────────────────────────
    # Lifecycle
    # ─────────────────────────────────────────────────────────────────

    async def run(self) -> None:
        try:
            self.symbols = await get_top_usdt_pairs(self.rest)
            logger.info(
                f"Top {len(self.symbols)} USDT pairs: "
                f"{', '.join(self.symbols[:10])}..."
            )

            await warmup_all(self.rest, self.symbols, list(TIMEFRAMES), self.state)
            await self.signal_logger.init()

            await self.notifier.send(
                f"🟢 <b>Scanner v2.1 started</b> (Order Book Layer)\n"
                f"Monitoring <b>{len(self.symbols)}</b> USDT pairs\n"
                f"Detectors (8): Velocity, Taker Imbalance, Whale, Volume Anomaly, "
                f"Multi-TF Pattern, OBI, Static Walls, Wall Absorption\n"
                f"Tiers: WATCH 50 / STRONG 70 / PREMIUM 85"
            )

            # Список всех потоков: aggTrade + 3 kline + depth20
            streams: List[str] = []
            for s in self.symbols:
                low = s.lower()
                streams.append(f"{low}@aggTrade")
                for tf in TIMEFRAMES:
                    streams.append(f"{low}@kline_{tf}")
                streams.append(f"{low}@depth20@100ms")

            logger.info(f"Total streams: {len(streams)}")
            ws = WebSocketManager(streams, self.handle_ws_message)
            await ws.run_forever()
        finally:
            await self.followup.shutdown()
            await self.signal_logger.close()
            await self.notifier.close()
            await self.rest.close()
