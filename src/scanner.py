"""
Scanner v2 — главный оркестратор.

Hot path:
  WebSocket message → parse → update state → run detectors → score → maybe_alert

Все операции async и неблокирующие. Один event loop.
"""
import logging
from typing import List

from config import TIMEFRAMES
from src.alerts.followup import FollowupScheduler
from src.alerts.manager import AlertManager
from src.core.state import Candle, GlobalState, SymbolState, Trade
from src.data.binance_rest import BinanceREST
from src.data.pairs import get_top_usdt_pairs
from src.data.warmup import warmup_all
from src.data.ws_manager import WebSocketManager
from src.detectors.multi_tf_pattern import detect_multi_tf_pattern
from src.detectors.taker_imbalance import detect_taker_imbalance
from src.detectors.velocity import detect_velocity
from src.detectors.volume_anomaly import detect_volume_anomaly
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
    # Hot path: WebSocket message handler
    # ─────────────────────────────────────────────────────────────────

    async def handle_ws_message(self, msg: dict) -> None:
        # Combined-stream формат: {"stream": "...", "data": {...}}
        data = msg.get("data")
        if not data:
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

        # Запускаем trade-driven детекторы. Они работают на trade-buffer.
        signals = []
        for detector in (
            detect_velocity,
            detect_taker_imbalance,
            detect_whale_trades,
            detect_volume_anomaly,
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
                state.current_5m = None  # свеча закрылась
                # На закрытии 5m — запускаем тяжёлый pattern-детектор
                pattern_sig = detect_multi_tf_pattern(state)
                if pattern_sig is not None:
                    # Combine с активными trade-driven сигналами в ту же сторону
                    extra = []
                    for det in (
                        detect_velocity,
                        detect_taker_imbalance,
                        detect_whale_trades,
                    ):
                        s = det(state)
                        if s and s.direction == pattern_sig.direction:
                            extra.append(s)
                    result = aggregate([pattern_sig] + extra)
                    await self.alert_manager.maybe_alert(state, result, candle.close)
            else:
                # Свеча в моменте — обновляем current_5m, чтобы Volume Anomaly мог его видеть
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
                f"🟢 <b>Scanner v2 started</b>\n"
                f"Monitoring <b>{len(self.symbols)}</b> USDT pairs\n"
                f"Detectors: Velocity, Taker Imbalance, Whale, Volume Anomaly, Multi-TF Pattern\n"
                f"Mode: Spot-only (BULLISH alerts), tiers: WATCH 50 / STRONG 70 / PREMIUM 85"
            )

            # Собираем список потоков: aggTrade + kline для каждого ТФ
            streams: List[str] = []
            for s in self.symbols:
                low = s.lower()
                streams.append(f"{low}@aggTrade")
                for tf in TIMEFRAMES:
                    streams.append(f"{low}@kline_{tf}")

            ws = WebSocketManager(streams, self.handle_ws_message)
            await ws.run_forever()
        finally:
            await self.followup.shutdown()
            await self.signal_logger.close()
            await self.notifier.close()
            await self.rest.close()
