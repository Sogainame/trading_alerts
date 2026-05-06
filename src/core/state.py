"""
Типы данных и in-memory state.

State — lock-free dict + deque. Работает потому что весь scanner живёт
в одном asyncio event loop без threads. Никаких Lock'ов на горячем пути.
"""
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Tuple


@dataclass
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


@dataclass
class WallEvent:
    """
    Запись о появлении/исчезновении крупного ордера на конкретной цене.
    Используется для anti-spoof фильтра (Static Wall) и Wall Absorption детектора.
    """
    price: float
    side: str               # "bid" | "ask"
    size: float             # количество монет
    notional: float         # size × price (USD)
    first_seen_ts: float    # секунды
    last_seen_ts: float
    last_size: float = 0.0  # последний размер на этом уровне (для absorption)
    initial_size: float = 0.0
    initial_notional: float = 0.0


@dataclass
class OrderBookState:
    """
    Состояние стакана для одной пары.
    Bids/asks — это полный snapshot top-20 уровней, обновляется через depth20@100ms.
    Каждый уровень = (price, quantity).

    История стен (level_history) нужна для двух целей:
      1. Понимать сколько секунд большой ордер сидит на месте (anti-spoof)
      2. Детектить когда ордер был большой, потом "съели" (Wall Absorption)
    """
    bids: List[Tuple[float, float]] = field(default_factory=list)  # отсортированы по убыванию цены
    asks: List[Tuple[float, float]] = field(default_factory=list)  # отсортированы по возрастанию цены
    last_update_ts: float = 0.0

    # Маппинг (side, price) → WallEvent. Хранит активные крупные уровни.
    level_history: Dict[Tuple[str, float], WallEvent] = field(default_factory=dict)

    # Недавние absorption-события: (timestamp, side, price, initial_notional)
    recent_absorptions: Deque[Tuple[float, str, float, float]] = field(
        default_factory=lambda: deque(maxlen=50)
    )

    @property
    def best_bid(self) -> Optional[float]:
        return self.bids[0][0] if self.bids else None

    @property
    def best_ask(self) -> Optional[float]:
        return self.asks[0][0] if self.asks else None

    @property
    def mid_price(self) -> Optional[float]:
        if self.best_bid is not None and self.best_ask is not None:
            return (self.best_bid + self.best_ask) / 2
        return None


@dataclass
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


@dataclass
class SymbolState:
    """All in-memory state for one trading pair."""
    symbol: str
    trades: Deque[Trade] = field(default_factory=lambda: deque(maxlen=500))
    candles_5m: Deque[Candle] = field(default_factory=lambda: deque(maxlen=50))
    candles_15m: Deque[Candle] = field(default_factory=lambda: deque(maxlen=30))
    candles_1h: Deque[Candle] = field(default_factory=lambda: deque(maxlen=24))
    current_5m: Optional[Candle] = None  # форма-в-моменте (intra-candle)
    order_book: OrderBookState = field(default_factory=OrderBookState)
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
