"""Тесты trade-driven детекторов: фейковые trades + check сигналов."""
from src.core.state import Candle, SymbolState, Trade
from src.detectors.taker_imbalance import detect_taker_imbalance
from src.detectors.velocity import detect_velocity
from src.detectors.volume_anomaly import detect_volume_anomaly
from src.detectors.whale_trades import detect_whale_trades


def _t(ts_ms: int, price: float, qty: float, is_buyer_maker: bool) -> Trade:
    return Trade(timestamp=ts_ms, price=price, quantity=qty, is_buyer_maker=is_buyer_maker)


def test_velocity_bullish_spike():
    """Цена выросла на 1% за 30s → BULLISH сигнал."""
    st = SymbolState(symbol="TEST")
    base_ts = 1_700_000_000_000
    # Сначала trade на старте окна
    st.trades.append(_t(base_ts, 100.0, 1, False))
    # Через 5 сек цена 100.5
    st.trades.append(_t(base_ts + 5_000, 100.5, 1, False))
    # Через 25 сек ещё цена 101 (прирост 1% за 25s — внутри окна 30s)
    st.trades.append(_t(base_ts + 25_000, 101.0, 1, False))

    sig = detect_velocity(st)
    assert sig is not None
    assert sig.direction == "BULLISH"
    assert sig.score_contribution == 25
    assert "+1.00%" in sig.description


def test_velocity_bearish_dump():
    st = SymbolState(symbol="TEST")
    base_ts = 1_700_000_000_000
    st.trades.append(_t(base_ts, 100.0, 1, False))
    st.trades.append(_t(base_ts + 25_000, 99.0, 1, False))
    sig = detect_velocity(st)
    assert sig is not None
    assert sig.direction == "BEARISH"


def test_velocity_no_signal_below_threshold():
    """Цена выросла только на 0.1% — ниже порога 0.5%."""
    st = SymbolState(symbol="TEST")
    base_ts = 1_700_000_000_000
    st.trades.append(_t(base_ts, 100.0, 1, False))
    st.trades.append(_t(base_ts + 25_000, 100.1, 1, False))
    assert detect_velocity(st) is None


def test_taker_imbalance_bullish():
    """80% trades по объёму = market buys → BULLISH."""
    st = SymbolState(symbol="TEST")
    base_ts = 1_700_000_000_000
    # 25 trades за последние 60s, 20 из них buys (80%)
    for i in range(25):
        is_market_sell = i >= 20  # last 5 are sells
        st.trades.append(_t(base_ts + i * 1000, 100.0, 1.0, is_market_sell))
    sig = detect_taker_imbalance(st)
    assert sig is not None
    assert sig.direction == "BULLISH"
    assert "buys" in sig.description


def test_taker_imbalance_no_signal_balanced():
    st = SymbolState(symbol="TEST")
    base_ts = 1_700_000_000_000
    for i in range(25):
        is_market_sell = i % 2 == 0  # 50/50
        st.trades.append(_t(base_ts + i * 1000, 100.0, 1.0, is_market_sell))
    assert detect_taker_imbalance(st) is None


def test_taker_imbalance_below_min_trades():
    """Меньше TAKER_IMBALANCE_MIN_TRADES в окне → нет сигнала."""
    st = SymbolState(symbol="TEST")
    base_ts = 1_700_000_000_000
    for i in range(5):
        st.trades.append(_t(base_ts + i * 1000, 100.0, 1.0, False))
    assert detect_taker_imbalance(st) is None


def test_whale_trades_bullish():
    """3+ market buys ≥$50k за 60s → BULLISH."""
    st = SymbolState(symbol="TEST")
    base_ts = 1_700_000_000_000
    # 4 китовых market buys по $60k each
    for i in range(4):
        st.trades.append(_t(base_ts + i * 5000, 1000.0, 60.0, False))  # 1000*60=$60k
    sig = detect_whale_trades(st)
    assert sig is not None
    assert sig.direction == "BULLISH"
    assert "whale buys" in sig.description.lower()


def test_whale_trades_no_signal_too_few():
    st = SymbolState(symbol="TEST")
    base_ts = 1_700_000_000_000
    # Только 2 кита (нужно 3+)
    for i in range(2):
        st.trades.append(_t(base_ts + i * 5000, 1000.0, 60.0, False))
    assert detect_whale_trades(st) is None


def test_whale_trades_no_signal_too_small():
    """Trades по $40k — недостаточно крупные (нужно ≥$50k)."""
    st = SymbolState(symbol="TEST")
    base_ts = 1_700_000_000_000
    for i in range(5):
        st.trades.append(_t(base_ts + i * 5000, 1000.0, 40.0, False))  # 1000*40=$40k
    assert detect_whale_trades(st) is None


def test_volume_anomaly_intra_candle():
    """Текущая 5m свеча уже накопила 3x от среднего объёма."""
    st = SymbolState(symbol="TEST")
    # 20 закрытых свечей со средним объёмом 1000
    for i in range(20):
        st.candles_5m.append(Candle(
            open_time=i * 300_000, open=100, high=101, low=99, close=100.5,
            volume=1000.0, close_time=(i + 1) * 300_000 - 1, is_closed=True
        ))
    # Текущая (формирующаяся) — уже 3500 объёма
    st.current_5m = Candle(
        open_time=20 * 300_000, open=100, high=102, low=99.5, close=101.5,
        volume=3500.0, close_time=21 * 300_000 - 1, is_closed=False
    )
    sig = detect_volume_anomaly(st)
    assert sig is not None
    assert sig.direction == "BULLISH"  # close > open
    assert "intra-5m" in sig.description


def test_volume_anomaly_anti_spam():
    """После того как для свечи уже алертили, повторный детект не выдаёт сигнал."""
    st = SymbolState(symbol="TEST")
    for i in range(20):
        st.candles_5m.append(Candle(
            open_time=i * 300_000, open=100, high=101, low=99, close=100.5,
            volume=1000.0, close_time=(i + 1) * 300_000 - 1, is_closed=True
        ))
    open_time = 20 * 300_000
    st.current_5m = Candle(
        open_time=open_time, open=100, high=102, low=99.5, close=101.5,
        volume=3500.0, close_time=open_time + 300_000 - 1, is_closed=False
    )
    # Первый раз — есть сигнал
    assert detect_volume_anomaly(st) is not None
    # Имитируем что AlertManager пометил
    st.last_volume_anomaly_at = open_time
    # Второй раз для той же свечи — None
    assert detect_volume_anomaly(st) is None
