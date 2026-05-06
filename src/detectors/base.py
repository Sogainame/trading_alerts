"""
Базовый dataclass для сигнала любого детектора.
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Signal:
    detector_name: str
    direction: str            # "BULLISH" | "BEARISH"
    score_contribution: int
    description: str          # human-readable, попадёт в Telegram-алерт
    extra: Optional[dict] = field(default=None)
