"""
Scoring Engine.

Логика: сигналы в одну сторону складываются, противоположные сокращают друг друга.
Если итог по одной стороне ≥ score-порога — это алерт.

Tier:
  >= TIER_PREMIUM (85): 🔥 Premium
  >= TIER_STRONG  (70): 🟢 Strong
  >= TIER_WATCH   (50): 🟡 Watch
"""
from dataclasses import dataclass, field
from typing import List

from config import TIER_PREMIUM, TIER_STRONG, TIER_WATCH
from src.detectors.base import Signal


@dataclass
class ScoringResult:
    score: int
    direction: str  # "BULLISH" | "BEARISH" | "NEUTRAL"
    signals: List[Signal] = field(default_factory=list)

    @property
    def tier(self) -> str:
        if self.score >= TIER_PREMIUM:
            return "PREMIUM"
        if self.score >= TIER_STRONG:
            return "STRONG"
        if self.score >= TIER_WATCH:
            return "WATCH"
        return "NONE"


def aggregate(signals: List[Signal]) -> ScoringResult:
    if not signals:
        return ScoringResult(score=0, direction="NEUTRAL")

    bull = [s for s in signals if s.direction == "BULLISH"]
    bear = [s for s in signals if s.direction == "BEARISH"]
    bull_score = sum(s.score_contribution for s in bull)
    bear_score = sum(s.score_contribution for s in bear)

    if bull_score > bear_score:
        return ScoringResult(
            score=min(100, bull_score - bear_score),
            direction="BULLISH",
            signals=bull,
        )
    if bear_score > bull_score:
        return ScoringResult(
            score=min(100, bear_score - bull_score),
            direction="BEARISH",
            signals=bear,
        )
    # Ничья — не алертим
    return ScoringResult(score=0, direction="NEUTRAL")
