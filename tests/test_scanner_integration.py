"""
Интеграционный тест: симулируем поток WebSocket-сообщений через Scanner.handle_ws_message.
Проверяем что pipeline целиком работает: parse → state update → detectors → alert.
"""
import pytest

from src.core.state import GlobalState


def _agg_trade_msg(symbol, ts, price, qty, is_buyer_maker):
    return {
        "stream": f"{symbol.lower()}@aggTrade",
        "data": {
            "e": "aggTrade", "s": symbol, "T": ts,
            "p": str(price), "q": str(qty), "m": is_buyer_maker,
        },
    }


def _kline_msg(symbol, interval, open_time, o, h, l, c, v, is_closed):
    return {
        "stream": f"{symbol.lower()}@kline_{interval}",
        "data": {
            "e": "kline", "s": symbol,
            "k": {
                "t": open_time, "T": open_time + 60_000 - 1, "i": interval,
                "o": str(o), "h": str(h), "l": str(l), "c": str(c), "v": str(v),
                "x": is_closed,
            },
        },
    }


def _depth_msg(symbol, bids, asks):
    return {
        "stream": f"{symbol.lower()}@depth20@100ms",
        "data": {
            "bids": [[str(p), str(q)] for p, q in bids],
            "asks": [[str(p), str(q)] for p, q in asks],
        },
    }


@pytest.mark.asyncio
async def test_scanner_routes_messages_to_correct_state_buckets():
    """Проверяем что Scanner правильно роутит aggTrade / kline / depth в state."""
    from src.scanner import Scanner

    sc = Scanner()
    # Подменяем компоненты на фейки чтобы не открывать сеть
    class _Notif:
        async def send(self, *a, **kw): return {"message_id": 1}
        async def close(self): pass
    class _Logger:
        async def init(self): pass
        async def log_alert(self, **kw): return 1
        async def close(self): pass
    sc.notifier = _Notif()
    sc.signal_logger = _Logger()
    sc.alert_manager.notifier = sc.notifier
    sc.alert_manager.signal_logger = sc.signal_logger

    # Aggregated trade
    await sc.handle_ws_message(_agg_trade_msg("BTCUSDT", 1_700_000_000_000, 100.0, 1.0, False))
    assert "BTCUSDT" in sc.state.symbols
    st = sc.state.symbols["BTCUSDT"]
    assert len(st.trades) == 1
    assert st.trades[0].price == 100.0

    # Kline 5m closed
    await sc.handle_ws_message(_kline_msg(
        "BTCUSDT", "5m", 1_700_000_000_000, 100, 101, 99, 100.5, 50.0, is_closed=True
    ))
    assert len(st.candles_5m) == 1
    assert st.current_5m is None

    # Kline 5m forming
    await sc.handle_ws_message(_kline_msg(
        "BTCUSDT", "5m", 1_700_000_300_000, 100.5, 102, 100, 101.5, 30.0, is_closed=False
    ))
    assert st.current_5m is not None
    assert st.current_5m.close == 101.5
    assert len(st.candles_5m) == 1  # forming не добавился в closed

    # Kline 1h closed
    await sc.handle_ws_message(_kline_msg(
        "BTCUSDT", "1h", 1_700_000_000_000, 100, 102, 99, 101, 1000.0, is_closed=True
    ))
    assert len(st.candles_1h) == 1

    # Depth update
    await sc.handle_ws_message(_depth_msg(
        "BTCUSDT", bids=[(99.9, 10), (99.8, 5)], asks=[(100.0, 7), (100.1, 3)]
    ))
    assert st.order_book.best_bid == 99.9
    assert st.order_book.best_ask == 100.0


@pytest.mark.asyncio
async def test_scanner_skips_garbage_messages():
    """Невалидные/неполные сообщения не должны крашить scanner."""
    from src.scanner import Scanner
    sc = Scanner()

    # Пустое
    await sc.handle_ws_message({})
    # Без data
    await sc.handle_ws_message({"stream": "x"})
    # Без symbol в данных
    await sc.handle_ws_message({"data": {"e": "aggTrade"}})
    # Неизвестный event
    await sc.handle_ws_message({"data": {"e": "unknown", "s": "BTCUSDT"}})
    # Не должно быть ни state, ни exception
    assert "BTCUSDT" not in sc.state.symbols or len(sc.state.symbols.get("BTCUSDT").trades or []) == 0


@pytest.mark.asyncio
async def test_full_pipeline_generates_alert():
    """End-to-end: пара получает достаточно сигналов → AlertManager отправляет в (фейковый) Telegram."""
    from src.scanner import Scanner

    sc = Scanner()
    sent = []
    class _Notif:
        async def send(self, text, reply_to=None):
            sent.append(text)
            return {"message_id": 1}
        async def close(self): pass
    class _Logger:
        async def init(self): pass
        async def log_alert(self, **kw): return 1
        async def close(self): pass
    sc.notifier = _Notif()
    sc.signal_logger = _Logger()
    sc.alert_manager.notifier = sc.notifier
    sc.alert_manager.signal_logger = sc.signal_logger

    sym = "TESTUSDT"
    ts0 = 1_700_000_000_000

    # Прогрев: 25 трейдов с явным buy-imbalance + velocity
    for i in range(20):
        # Сначала рост от 100 до 100.0
        await sc.handle_ws_message(_agg_trade_msg(sym, ts0 + i * 1000, 100.0, 1.0, False))
    # Резкий импульс: цена прыгнула на 1.5% и большие buys
    for i in range(10):
        # Whale buys (qty * price = $50k+) с растущей ценой
        await sc.handle_ws_message(_agg_trade_msg(
            sym, ts0 + (20 + i) * 1000, 101.5, 600.0, False  # 101.5 * 600 = $60.9k whale buy
        ))

    # Должен быть как минимум один алерт (velocity + taker imbalance + whale)
    assert len(sent) > 0, "End-to-end pipeline не сгенерировал алерт"
    alert_text = sent[0]
    assert sym in alert_text
    assert "ВВЕРХ" in alert_text
