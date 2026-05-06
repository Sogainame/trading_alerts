"""Тесты scoring, форматтера, AlertManager (cooldown, dedup, ONLY_BULLISH фильтр)."""
import asyncio
import time

import pytest

from src.alerts.formatter import format_alert
from src.alerts.targets import Targets
from src.core.state import SymbolState
from src.detectors.base import Signal
from src.scoring.engine import ScoringResult, aggregate


def _sig(direction, score, name="X", desc="x"):
    return Signal(detector_name=name, direction=direction, score_contribution=score, description=desc)


def test_aggregate_one_direction():
    sigs = [_sig("BULLISH", 25), _sig("BULLISH", 20)]
    r = aggregate(sigs)
    assert r.direction == "BULLISH"
    assert r.score == 45
    assert len(r.signals) == 2


def test_aggregate_conflicting_directions_subtract():
    sigs = [_sig("BULLISH", 30), _sig("BEARISH", 20)]
    r = aggregate(sigs)
    assert r.direction == "BULLISH"
    assert r.score == 10


def test_aggregate_balanced_neutral():
    sigs = [_sig("BULLISH", 20), _sig("BEARISH", 20)]
    r = aggregate(sigs)
    assert r.direction == "NEUTRAL"
    assert r.score == 0


def test_aggregate_empty():
    r = aggregate([])
    assert r.direction == "NEUTRAL"
    assert r.score == 0


def test_aggregate_score_capped_at_100():
    sigs = [_sig("BULLISH", 50), _sig("BULLISH", 50), _sig("BULLISH", 50)]
    r = aggregate(sigs)
    assert r.score == 100


def test_tier_thresholds():
    assert ScoringResult(score=49, direction="BULLISH").tier == "NONE"
    assert ScoringResult(score=50, direction="BULLISH").tier == "WATCH"
    assert ScoringResult(score=70, direction="BULLISH").tier == "STRONG"
    assert ScoringResult(score=85, direction="BULLISH").tier == "PREMIUM"
    assert ScoringResult(score=100, direction="BULLISH").tier == "PREMIUM"


def test_format_alert_basic():
    sigs = [_sig("BULLISH", 25, "VELOCITY", "+1.2% за 30s")]
    res = ScoringResult(score=75, direction="BULLISH", signals=sigs)
    msg = format_alert("BTCUSDT", res, current_price=67432.5, targets=None)
    assert "STRONG" in msg
    assert "BTCUSDT" in msg
    assert "ВВЕРХ" in msg
    assert "+1.2% за 30s" in msg
    assert "(+25)" in msg


def test_format_alert_with_targets_includes_rr():
    sigs = [_sig("BULLISH", 80, "X", "test")]
    res = ScoringResult(score=80, direction="BULLISH", signals=sigs)
    targets = Targets(
        stop_price=99.0, stop_wall_usd=200_000, stop_distance_pct=1.0,
        target_price=102.0, target_wall_usd=300_000, target_distance_pct=2.0,
    )
    msg = format_alert("X", res, current_price=100.0, targets=targets)
    assert "ОРИЕНТИРЫ" in msg
    assert "Стоп" in msg
    assert "Цель" in msg
    assert "RR" in msg
    # Risk = 100 - 99 = 1, Reward = 102 - 100 = 2 → RR = 1:2
    assert "1:2.00" in msg


def test_format_alert_no_targets_block_for_bearish():
    """Spot-only — для bearish targets не показываем."""
    sigs = [_sig("BEARISH", 80, "X", "test")]
    res = ScoringResult(score=80, direction="BEARISH", signals=sigs)
    targets = Targets(stop_price=101.0, target_price=98.0)
    msg = format_alert("X", res, current_price=100.0, targets=targets)
    assert "ОРИЕНТИРЫ" not in msg


# ─────────────────────────────────────────────────────────────────
# AlertManager: cooldown, dedup, ONLY_BULLISH
# ─────────────────────────────────────────────────────────────────


class FakeNotifier:
    def __init__(self):
        self.sent = []
        self._mid = 0

    async def send(self, text, reply_to=None):
        self._mid += 1
        self.sent.append({"text": text, "reply_to": reply_to})
        return {"message_id": self._mid}

    async def close(self):
        pass


class FakeLogger:
    def __init__(self):
        self.alerts = []

    async def log_alert(self, **kwargs):
        self.alerts.append(kwargs)
        return len(self.alerts)

    async def init(self):
        pass

    async def close(self):
        pass


@pytest.mark.asyncio
async def test_alert_manager_sends_when_score_high_enough():
    from src.alerts.manager import AlertManager
    n, l = FakeNotifier(), FakeLogger()
    am = AlertManager(n, l)
    st = SymbolState(symbol="TEST")
    res = ScoringResult(score=70, direction="BULLISH", signals=[_sig("BULLISH", 70)])
    await am.maybe_alert(st, res, 100.0)
    assert len(n.sent) == 1
    assert len(l.alerts) == 1


@pytest.mark.asyncio
async def test_alert_manager_drops_below_threshold():
    from src.alerts.manager import AlertManager
    n, l = FakeNotifier(), FakeLogger()
    am = AlertManager(n, l)
    st = SymbolState(symbol="TEST")
    res = ScoringResult(score=49, direction="BULLISH", signals=[_sig("BULLISH", 49)])
    await am.maybe_alert(st, res, 100.0)
    assert len(n.sent) == 0


@pytest.mark.asyncio
async def test_alert_manager_drops_bearish_in_only_bullish():
    """ONLY_BULLISH=True (default) → bearish сигналы не уходят."""
    from src.alerts.manager import AlertManager
    n, l = FakeNotifier(), FakeLogger()
    am = AlertManager(n, l)
    st = SymbolState(symbol="TEST")
    res = ScoringResult(score=80, direction="BEARISH", signals=[_sig("BEARISH", 80)])
    await am.maybe_alert(st, res, 100.0)
    assert len(n.sent) == 0


@pytest.mark.asyncio
async def test_alert_manager_cooldown():
    """Второй алерт по той же паре в течение cooldown — пропускается."""
    from src.alerts.manager import AlertManager
    n, l = FakeNotifier(), FakeLogger()
    am = AlertManager(n, l)
    st = SymbolState(symbol="TEST")
    res = ScoringResult(score=80, direction="BULLISH", signals=[_sig("BULLISH", 80)])
    await am.maybe_alert(st, res, 100.0)
    await am.maybe_alert(st, res, 101.0)
    assert len(n.sent) == 1, "cooldown не сработал"

    # А вот когда симулируем что cooldown прошёл — алерт уйдёт
    st.last_alert_at = time.time() - 10_000  # давно
    await am.maybe_alert(st, res, 102.0)
    assert len(n.sent) == 2
