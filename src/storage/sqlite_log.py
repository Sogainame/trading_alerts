"""
Async SQLite логгер сигналов через aiosqlite.

Назначение: каждый отправленный алерт пишется в БД с разбивкой по детекторам.
Через 2 недели работы можно посчитать win-rate каждого детектора и каждого тира,
и тюнить веса по реальным данным.

Не блокирует горячий путь — все INSERT'ы async.
"""
import json
import logging
import os
import time
from typing import List, Optional

import aiosqlite

from config import DB_PATH
from src.detectors.base import Signal

logger = logging.getLogger(__name__)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    symbol TEXT NOT NULL,
    score INTEGER NOT NULL,
    tier TEXT NOT NULL,
    direction TEXT NOT NULL,
    price REAL NOT NULL,
    detectors_json TEXT NOT NULL,
    message_id INTEGER
);

CREATE INDEX IF NOT EXISTS idx_alerts_symbol ON alerts(symbol);
CREATE INDEX IF NOT EXISTS idx_alerts_timestamp ON alerts(timestamp);
CREATE INDEX IF NOT EXISTS idx_alerts_tier ON alerts(tier);

CREATE TABLE IF NOT EXISTS followups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id INTEGER NOT NULL,
    delay_seconds INTEGER NOT NULL,
    timestamp REAL NOT NULL,
    price REAL NOT NULL,
    pct_change REAL NOT NULL,
    FOREIGN KEY (alert_id) REFERENCES alerts(id)
);

CREATE INDEX IF NOT EXISTS idx_followups_alert ON followups(alert_id);
"""


class SignalLogger:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None

    async def init(self) -> None:
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        self._db = await aiosqlite.connect(self.db_path)
        # WAL mode = быстрые писи + читалки могут идти параллельно
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA synchronous=NORMAL")
        await self._db.executescript(_SCHEMA)
        await self._db.commit()
        logger.info(f"SQLite logger initialized at {self.db_path}")

    async def log_alert(
        self,
        symbol: str,
        score: int,
        tier: str,
        direction: str,
        price: float,
        signals: List[Signal],
        message_id: Optional[int] = None,
    ) -> Optional[int]:
        if self._db is None:
            return None
        detectors_data = [
            {
                "name": s.detector_name,
                "score": s.score_contribution,
                "description": s.description,
                "extra": s.extra,
            }
            for s in signals
        ]
        try:
            cursor = await self._db.execute(
                """
                INSERT INTO alerts
                  (timestamp, symbol, score, tier, direction, price, detectors_json, message_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    time.time(),
                    symbol,
                    score,
                    tier,
                    direction,
                    price,
                    json.dumps(detectors_data),
                    message_id,
                ),
            )
            await self._db.commit()
            return cursor.lastrowid
        except Exception:
            logger.exception(f"Failed to log alert for {symbol}")
            return None

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None
