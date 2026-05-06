"""
Targets calculator — находит ближайший крупный bid wall (логичный стоп)
и ближайший крупный ask wall (логичная цель), считает risk-reward.

Используется в format_alert чтобы показать пользователю:
  - где разумно поставить стоп (под ближайшей крупной поддержкой)
  - где разумная цель (перед ближайшим крупным сопротивлением)
  - какое RR получается

Это НЕ авто-исполнение, просто ориентиры. Пользователь решает сам.
"""
import time
from dataclasses import dataclass
from typing import Optional

from config import (
    STATIC_WALL_MIN_LIFETIME_SECONDS,
    TARGET_MAX_DISTANCE_PCT,
    TARGET_MIN_WALL_USD,
)
from src.core.state import SymbolState


@dataclass
class Targets:
    stop_price: Optional[float] = None        # под bid wall
    stop_wall_usd: Optional[float] = None
    stop_distance_pct: Optional[float] = None  # на сколько % ниже текущей цены

    target_price: Optional[float] = None       # перед ask wall
    target_wall_usd: Optional[float] = None
    target_distance_pct: Optional[float] = None

    @property
    def has_full_setup(self) -> bool:
        return self.stop_price is not None and self.target_price is not None

    @property
    def risk_reward(self) -> Optional[float]:
        """RR = (цель − вход) / (вход − стоп). Считается в format_alert
        с учётом текущей цены."""
        return None  # вычисляется в форматтере, тут только данные


def find_targets(state: SymbolState, current_price: float) -> Targets:
    """
    Идём по level_history, ищем самые близкие к current_price крупные стены:
      - Снизу (bid) которые живут ≥ STATIC_WALL_MIN_LIFETIME_SECONDS — кандидат на стоп
      - Сверху (ask) которые живут ≥ STATIC_WALL_MIN_LIFETIME_SECONDS — кандидат на цель

    Берём САМЫЕ БЛИЖАЙШИЕ к цене, а не самые крупные —
    логика "что встретится первым".
    """
    ob = state.order_book
    targets = Targets()
    now = time.time()

    closest_bid_wall = None
    closest_ask_wall = None
    bid_wall_size = None
    ask_wall_size = None

    for (side, price), event in ob.level_history.items():
        # Только статические стены (anti-spoof)
        lifetime = now - event.first_seen_ts
        if lifetime < STATIC_WALL_MIN_LIFETIME_SECONDS:
            continue
        if event.notional < TARGET_MIN_WALL_USD:
            continue

        # Не смотрим стены слишком далеко от цены
        distance_pct = abs(current_price - price) / current_price * 100
        if distance_pct > TARGET_MAX_DISTANCE_PCT:
            continue

        if side == "bid" and price < current_price:
            # Кандидат на стоп — берём самую близкую к цене (т.е. самую высокую)
            if closest_bid_wall is None or price > closest_bid_wall:
                closest_bid_wall = price
                bid_wall_size = event.notional
        elif side == "ask" and price > current_price:
            # Кандидат на цель — берём самую близкую к цене (самую низкую)
            if closest_ask_wall is None or price < closest_ask_wall:
                closest_ask_wall = price
                ask_wall_size = event.notional

    if closest_bid_wall is not None:
        targets.stop_price = closest_bid_wall
        targets.stop_wall_usd = bid_wall_size
        targets.stop_distance_pct = (current_price - closest_bid_wall) / current_price * 100

    if closest_ask_wall is not None:
        targets.target_price = closest_ask_wall
        targets.target_wall_usd = ask_wall_size
        targets.target_distance_pct = (closest_ask_wall - current_price) / current_price * 100

    return targets
