"""Тесты SignalLogger: реально создаёт SQLite БД, пишет/читает alerts."""
import os
import tempfile

import aiosqlite
import pytest

from src.detectors.base import Signal


@pytest.mark.asyncio
async def test_sqlite_logger_init_and_insert():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        # Подменяем DB_PATH через переинициализацию объекта с явным path
        from src.storage.sqlite_log import SignalLogger
        sl = SignalLogger(db_path=db_path)
        await sl.init()

        sigs = [
            Signal("VELOCITY", "BULLISH", 25, "+1.2% за 30s"),
            Signal("WHALE_BUYS", "BULLISH", 20, "3 whale buys"),
        ]
        alert_id = await sl.log_alert(
            symbol="BTCUSDT",
            score=75,
            tier="STRONG",
            direction="BULLISH",
            price=67432.5,
            signals=sigs,
            message_id=42,
        )
        assert alert_id is not None
        await sl.close()

        # Открываем БД отдельным connection и читаем что записалось
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute("SELECT symbol, score, tier, price, message_id FROM alerts")
            rows = await cursor.fetchall()
        assert len(rows) == 1
        assert rows[0] == ("BTCUSDT", 75, "STRONG", 67432.5, 42)


@pytest.mark.asyncio
async def test_sqlite_logger_no_followups_table():
    """После удаления followup-фичи таблицы followups быть НЕ должно."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        from src.storage.sqlite_log import SignalLogger
        sl = SignalLogger(db_path=db_path)
        await sl.init()
        await sl.close()

        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = [r[0] for r in await cursor.fetchall()]
        assert "alerts" in tables
        assert "followups" not in tables, (
            f"Таблица followups не должна существовать после удаления фичи. Tables: {tables}"
        )
