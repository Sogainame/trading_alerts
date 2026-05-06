"""
Обработчик depth20@100ms сообщений.

Что делает на каждое сообщение:
  1. Обновляет bids/asks в SymbolState.order_book
  2. Для каждого уровня в первых TOP_LEVELS:
     - Если это крупный ордер (≥ STATIC_WALL_MIN_USD) — заводит/обновляет WallEvent
       чтобы трекать как давно он там стоит (для anti-spoof)
     - Если уровень был крупным (есть WallEvent), но размер упал ≤ ABSORPTION_REMNANT_PCT
       от изначального — это absorption-событие (стену съели)

Почему это важно: depth20@100ms прилетает 10 раз в секунду на каждую пару, поэтому
вся логика ОЧЕНЬ быстрая. Никаких внешних вызовов, чистая работа со state.
"""
import time

from config import (
    ABSORPTION_MIN_INITIAL_USD,
    ABSORPTION_REMNANT_PCT,
    STATIC_WALL_MIN_USD,
    STATIC_WALL_TOP_LEVELS,
)
from src.core.state import OrderBookState, SymbolState, WallEvent


def handle_depth_message(state: SymbolState, data: dict) -> None:
    """
    Binance depth20@100ms message format:
    {
        "lastUpdateId": ...,
        "bids": [["price", "qty"], ...],  # 20 уровней
        "asks": [["price", "qty"], ...]
    }
    """
    bids_raw = data.get("bids") or data.get("b")
    asks_raw = data.get("asks") or data.get("a")
    if not bids_raw or not asks_raw:
        return

    # Парсим в list of (price, qty) — float операции в ~10x быстрее чем Decimal
    bids = [(float(b[0]), float(b[1])) for b in bids_raw]
    asks = [(float(a[0]), float(a[1])) for a in asks_raw]

    ob = state.order_book
    ob.bids = bids
    ob.asks = asks
    now = time.time()
    ob.last_update_ts = now

    _update_wall_tracking(ob, bids, "bid", now)
    _update_wall_tracking(ob, asks, "ask", now)
    _cleanup_stale_walls(ob, bids, asks, now)


def _update_wall_tracking(
    ob: OrderBookState, levels: list, side: str, now: float
) -> None:
    """
    Идём по топ-N уровням, обновляем WallEvent для тех что больше порога.
    Заодно детектим absorption: если у нас был активный wall, а текущий размер
    стал маленьким — это event для recent_absorptions.
    """
    seen_prices = set()
    for i, (price, qty) in enumerate(levels[:STATIC_WALL_TOP_LEVELS]):
        notional = price * qty
        seen_prices.add(price)
        key = (side, price)
        existing = ob.level_history.get(key)

        if notional >= STATIC_WALL_MIN_USD:
            # Крупный ордер — заводим или апдейтим
            if existing is None:
                ob.level_history[key] = WallEvent(
                    price=price,
                    side=side,
                    size=qty,
                    notional=notional,
                    first_seen_ts=now,
                    last_seen_ts=now,
                    last_size=qty,
                    initial_size=qty,
                    initial_notional=notional,
                )
            else:
                existing.size = qty
                existing.notional = notional
                existing.last_size = qty
                existing.last_seen_ts = now
        else:
            # Уровень не крупный сейчас. Но если он был крупным и резко уменьшился —
            # это потенциальное absorption-событие.
            if existing is not None and existing.initial_notional >= ABSORPTION_MIN_INITIAL_USD:
                shrink_ratio = qty / existing.initial_size if existing.initial_size > 0 else 0
                if shrink_ratio <= ABSORPTION_REMNANT_PCT:
                    # Wall сильно сократился = его поглотили
                    ob.recent_absorptions.append(
                        (now, side, price, existing.initial_notional)
                    )
                    del ob.level_history[key]
                else:
                    # Просто частичное уменьшение — обновляем, продолжаем трекать
                    existing.last_size = qty
                    existing.last_seen_ts = now


def _cleanup_stale_walls(
    ob: OrderBookState, bids: list, asks: list, now: float
) -> None:
    """
    Если уровень исчез из топ-20 (не в наших данных вообще) — это тоже absorption,
    если он был крупным. Иначе ордер мог быть отменён, считаем как absorption всё равно
    (для downstream-детектора это важно: путь освободился).

    Удаляем уровни старше 5 минут чтобы dict не рос бесконечно.
    """
    bid_prices = {p for p, _ in bids[:STATIC_WALL_TOP_LEVELS]}
    ask_prices = {p for p, _ in asks[:STATIC_WALL_TOP_LEVELS]}

    to_delete = []
    for key, event in ob.level_history.items():
        side, price = key
        present = price in (bid_prices if side == "bid" else ask_prices)

        if not present:
            # Уровень полностью пропал из топа
            if event.initial_notional >= ABSORPTION_MIN_INITIAL_USD:
                ob.recent_absorptions.append(
                    (now, side, price, event.initial_notional)
                )
            to_delete.append(key)
            continue

        # Stale cleanup — старше 5 минут без обновлений = удаляем
        if now - event.last_seen_ts > 300:
            to_delete.append(key)

    for key in to_delete:
        ob.level_history.pop(key, None)
