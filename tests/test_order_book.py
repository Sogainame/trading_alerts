"""
Тесты Order Book Layer:
  - depth handler парсинг
  - детекторы OBI / Static Wall / Wall Absorption
  - проверка фикса 'stale wall' (важно после последнего бага)
  - targets calculation
"""
from src.alerts.targets import find_targets
from src.core.state import SymbolState
from src.data.order_book_handler import handle_depth_message
from src.detectors.order_book_imbalance import detect_order_book_imbalance
from src.detectors.static_wall import detect_static_wall_support
from src.detectors.wall_absorption import detect_wall_absorption


def _depth_msg(bids, asks):
    return {
        "bids": [[str(p), str(q)] for p, q in bids],
        "asks": [[str(p), str(q)] for p, q in asks],
    }


def test_depth_parsing_basic():
    st = SymbolState(symbol="TEST")
    msg = _depth_msg(
        bids=[(100.0, 1.0), (99.9, 5.0), (99.8, 10.0)],
        asks=[(100.1, 2.0), (100.2, 3.0)],
    )
    handle_depth_message(st, msg)
    assert st.order_book.best_bid == 100.0
    assert st.order_book.best_ask == 100.1
    assert st.order_book.mid_price == 100.05
    assert len(st.order_book.bids) == 3
    assert len(st.order_book.asks) == 2


def test_obi_bullish():
    """Bid notional >> ask notional → BULLISH сигнал."""
    st = SymbolState(symbol="TEST")
    bids = [(100, 100)] * 20  # 20 уровней по $10k = $200k
    asks = [(101, 1)] * 20    # 20 уровней по $101 = $2020
    handle_depth_message(st, _depth_msg(bids, asks))
    sig = detect_order_book_imbalance(st)
    assert sig is not None
    assert sig.direction == "BULLISH"


def test_obi_bearish():
    st = SymbolState(symbol="TEST")
    bids = [(100, 1)] * 20
    asks = [(101, 100)] * 20
    handle_depth_message(st, _depth_msg(bids, asks))
    sig = detect_order_book_imbalance(st)
    assert sig is not None
    assert sig.direction == "BEARISH"


def test_obi_no_signal_balanced():
    st = SymbolState(symbol="TEST")
    bids = [(100, 10)] * 20
    asks = [(101, 10)] * 20
    handle_depth_message(st, _depth_msg(bids, asks))
    assert detect_order_book_imbalance(st) is None


def test_static_wall_lifetime_gating():
    """Wall появился только что — НЕТ сигнала. Только после ≥30s lifetime."""
    st = SymbolState(symbol="TEST")
    # Поставим стену $200k на 99.0 (ниже best bid)
    bids = [(100, 1), (99, 2000)]  # 99×2000=$198k — wall
    asks = [(100.5, 1)]
    handle_depth_message(st, _depth_msg(bids, asks))
    # Сразу — None (свежеоткрытая стена, не прошёл anti-spoof)
    assert detect_static_wall_support(st) is None
    # Перематываем first_seen на 35 секунд назад
    for ev in st.order_book.level_history.values():
        ev.first_seen_ts -= 35
    sig = detect_static_wall_support(st)
    assert sig is not None
    assert sig.direction == "BULLISH"
    assert "Поддержка" in sig.description


def test_static_wall_disappears_after_size_drop():
    """ФИКС БАГА: если wall уменьшился ниже порога — больше не учитывается."""
    st = SymbolState(symbol="TEST")
    # 1. Заводим большую стену
    bids = [(100, 1), (99, 5000)]  # $495k — мега-wall
    handle_depth_message(st, _depth_msg(bids, [(100.5, 1)]))

    # Перематываем lifetime
    for ev in st.order_book.level_history.values():
        ev.first_seen_ts -= 60

    # До уменьшения — есть сигнал
    sig1 = detect_static_wall_support(st)
    assert sig1 is not None
    initial_notional = sig1.extra["wall_notional"]
    assert initial_notional > 400_000

    # 2. Wall уменьшился до $50k (ниже STATIC_WALL_MIN_USD=$100k, но не absorption)
    bids = [(100, 1), (99, 500)]  # $49.5k
    handle_depth_message(st, _depth_msg(bids, [(100.5, 1)]))

    # После уменьшения — wall больше НЕ должен фигурировать
    sig2 = detect_static_wall_support(st)
    assert sig2 is None, (
        f"BUG: после уменьшения wall до $49.5k детектор всё ещё нашёл стену "
        f"({sig2.extra if sig2 else 'no'}). Это та самая проблема что Fedor нашёл с TAOUSDT."
    )

    # И в level_history его быть не должно
    assert ("bid", 99.0) not in st.order_book.level_history


def test_wall_absorption_ask_eaten():
    """Большая ask стена сверху → исчезла → BULLISH absorption сигнал."""
    st = SymbolState(symbol="TEST")
    # 1. Большая ask на 102 (за пределами 20 уровней? нет — пусть будет рядом)
    asks = [(101, 1), (102, 5000)]  # 102×5000 = $510k
    bids = [(100, 1)]
    handle_depth_message(st, _depth_msg(bids, asks))

    # 2. Wall полностью исчез из стакана (отозван или съеден маркет-баями)
    asks = [(101, 1)]  # уровень 102 ушёл
    handle_depth_message(st, _depth_msg(bids, asks))

    sig = detect_wall_absorption(st)
    assert sig is not None
    assert sig.direction == "BULLISH"  # ask съели → путь вверх свободен
    assert "ask-стена" in sig.description.lower()


def test_targets_calculation():
    """Когда есть статические стены — targets находит ближайшие."""
    st = SymbolState(symbol="TEST")
    # bids: stена $200k на 99.5
    # asks: стена $300k на 100.5
    bids = [(100, 1), (99.9, 1), (99.5, 2000)]
    asks = [(100.1, 1), (100.5, 3000)]
    handle_depth_message(st, _depth_msg(bids, asks))
    # Перематываем lifetime
    for ev in st.order_book.level_history.values():
        ev.first_seen_ts -= 60

    targets = find_targets(st, current_price=100.0)
    assert targets.stop_price == 99.5
    assert targets.target_price == 100.5
    assert targets.has_full_setup is True
    # Distance check
    assert abs(targets.stop_distance_pct - 0.5) < 0.01
    assert abs(targets.target_distance_pct - 0.5) < 0.01


def test_targets_skips_stale_walls():
    """Walls которые не прожили достаточно — не используются как targets."""
    st = SymbolState(symbol="TEST")
    bids = [(100, 1), (99.5, 2000)]
    asks = [(100.5, 3000)]
    handle_depth_message(st, _depth_msg(bids, asks))
    # НЕ перематываем — стены свежие
    targets = find_targets(st, current_price=100.0)
    assert targets.stop_price is None
    assert targets.target_price is None
