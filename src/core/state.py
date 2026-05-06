"""
Типы данных и in-memory state.

State — lock-free dict + deque. Работает потому что весь scanner живёт
в одном asyncio event loop без threads. Никаких Lock'ов на горячем пути.
"""
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional


@dataclass(slots=True)
class Trade:
    """Aggregated trade from @aggTrade stream."""
    timestamp: int      # ms
    price: float
    quantity: float
    is_buyer_maker: bool

    @property
    def notional(self) -> float:
        return self.price * self.quantity

    @property
    def is_market_buy(self) -> bool:
        # is_buyer_maker == False → taker — это buyer (он "съел" ask) → market buy
        return not self.is_buyer_maker


@dataclass(slots=True)
class Candle:
    open_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    close_time: int
    is_closed: bool = True

    @classmethod
    def from_ws_kline(cls, k: dict, is_closed: bool) -> "Candle":
        return cls(
            open_time=k["t"],
            open=float(k["o"]),
            high=float(k["h"]),
            low=float(k["l"]),
            close=float(k["c"]),
            volume=float(k["v"]),
            close_time=k["T"],
            is_closed=is_closed,
        )

    @classmethod
    def from_rest(cls, kline: list) -> "Candle":
        return cls(
            open_time=kline[0],
            open=float(kline[1]),
            high=float(kline[2]),
            low=float(kline[3]),
            close=float(kline[4]),
            volume=float(kline[5]),
            close_time=kline[6],
            is_closed=True,
        )


@dataclass(slots=True)
class SymbolState:
    """All in-memory state for one trading pair."""
    symbol: str
    trades: Deque[Trade] = field(default_factory=lambda: deque(maxlen=500))
    candles_5m: Deque[Candle] = field(default_factory=lambda: deque(maxlen=50))
    candles_15m: Deque[Candle] = field(default_factory=lambda: deque(maxlen=30))
    candles_1h: Deque[Candle] = field(default_factory=lambda: deque(maxlen=24))
    current_5m: Optional[Candle] = None  # форма-в-моменте (intra-candle)
    last_alert_at: float = 0.0
    last_alert_score: int = 0
    last_volume_anomaly_at: int = 0  # open_time свечи где уже алертили — анти-спам


class GlobalState:
    """Маппинг symbol → SymbolState."""

    def __init__(self) -> None:
        self.symbols: Dict[str, SymbolState] = {}

    def get_or_create(self, symbol: str) -> SymbolState:
        st = self.symbols.get(symbol)
        if st is None:
            st = SymbolState(symbol=symbol)
            self.symbols[symbol] = st
        return st

    def all(self) -> List[SymbolState]:
        return list(self.symbols.values())
