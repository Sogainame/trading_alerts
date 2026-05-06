"""Хранилище последних N свечей по каждой паре в оперативной памяти."""
from collections import deque
from typing import Deque, Dict, List

import numpy as np

from config import CANDLE_BUFFER_SIZE


class Candle:
    """Закрытая свеча Binance: OHLCV + временные метки."""

    __slots__ = ("open_time", "open", "high", "low", "close", "volume", "close_time")

    def __init__(
        self,
        open_time: int,
        o: float,
        h: float,
        l: float,
        c: float,
        v: float,
        close_time: int,
    ):
        self.open_time = open_time
        self.open = o
        self.high = h
        self.low = l
        self.close = c
        self.volume = v
        self.close_time = close_time

    @classmethod
    def from_ws_kline(cls, k: dict) -> "Candle":
        """Создать из объекта `k` внутри сообщения kline-стрима Binance."""
        return cls(
            open_time=k["t"],
            o=float(k["o"]),
            h=float(k["h"]),
            l=float(k["l"]),
            c=float(k["c"]),
            v=float(k["v"]),
            close_time=k["T"],
        )

    @classmethod
    def from_rest(cls, kline: list) -> "Candle":
        """Создать из массива REST API: [open_time, o, h, l, c, v, close_time, ...]."""
        return cls(
            open_time=kline[0],
            o=float(kline[1]),
            h=float(kline[2]),
            l=float(kline[3]),
            c=float(kline[4]),
            v=float(kline[5]),
            close_time=kline[6],
        )

    def is_bullish(self) -> bool:
        return self.close > self.open

    def __repr__(self) -> str:
        return (
            f"Candle(t={self.open_time}, o={self.open}, h={self.high}, "
            f"l={self.low}, c={self.close}, v={self.volume})"
        )


class CandleBuffer:
    """Кольцевой буфер на каждый символ. Максимум CANDLE_BUFFER_SIZE свечей."""

    def __init__(self, size: int = CANDLE_BUFFER_SIZE):
        self.size = size
        self._buffers: Dict[str, Deque[Candle]] = {}

    def add(self, symbol: str, candle: Candle) -> None:
        """Добавить новую закрытую свечу."""
        if symbol not in self._buffers:
            self._buffers[symbol] = deque(maxlen=self.size)
        self._buffers[symbol].append(candle)

    def init(self, symbol: str, candles: List[Candle]) -> None:
        """Инициализировать буфер сразу пачкой исторических свечей."""
        self._buffers[symbol] = deque(candles[-self.size:], maxlen=self.size)

    def get(self, symbol: str) -> List[Candle]:
        return list(self._buffers.get(symbol, []))

    def is_ready(self, symbol: str, min_candles: int) -> bool:
        return len(self._buffers.get(symbol, [])) >= min_candles

    def to_arrays(self, symbol: str) -> dict:
        """Вернуть OHLCV как numpy массивы — формат, который ест TA-Lib."""
        candles = self._buffers.get(symbol, [])
        return {
            "open": np.array([c.open for c in candles], dtype=np.float64),
            "high": np.array([c.high for c in candles], dtype=np.float64),
            "low": np.array([c.low for c in candles], dtype=np.float64),
            "close": np.array([c.close for c in candles], dtype=np.float64),
            "volume": np.array([c.volume for c in candles], dtype=np.float64),
        }
