"""
Cooldown — не слать алерты по одной паре чаще, чем раз в N секунд.
Защита от спама когда несколько свечей подряд триггерят паттерны.
"""
import time
from typing import Dict

from config import ALERT_COOLDOWN_SECONDS


class CooldownFilter:
    def __init__(self, cooldown_seconds: int = ALERT_COOLDOWN_SECONDS):
        self.cooldown = cooldown_seconds
        self._last_alert: Dict[str, float] = {}

    def can_alert(self, symbol: str) -> bool:
        now = time.time()
        last = self._last_alert.get(symbol, 0.0)
        return (now - last) >= self.cooldown

    def mark_alerted(self, symbol: str) -> None:
        self._last_alert[symbol] = time.time()
