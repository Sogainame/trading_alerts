"""
Получение топ-N USDT пар по выбранному критерию.

Логика:
  1. Отфильтровать только USDT-пары
  2. Отбросить стейблкоины и фиаты
  3. Применить минимальный фильтр по 24h объёму (защита от illiquid pump-говна)
  4. Применить минимальный фильтр по волатильности (только "движущиеся" монеты)
  5. Ранжировать по выбранной метрике (RANKING_METRIC):
       - volatility_range: (high - low) / weightedAvg * 100  (range volatility)
       - price_change_abs: |priceChangePercent|              (24h directional move)
       - volume:           quoteVolume                       (старое поведение)
  6. Вернуть top-N

Для скальпинга на горках по умолчанию = volatility_range. Это соответствует
тому, как трейдеры выбирают монеты вручную: ищут пары с большим суточным
размахом — там есть на чём заработать на осцилляциях.
"""
import logging
from typing import List

from config import (
    EXCLUDE_SYMBOLS,
    MIN_DAILY_VOLUME_USD,
    MIN_VOLATILITY_RANGE_PCT,
    RANKING_METRIC,
    TOP_N_PAIRS,
)
from src.data.binance_rest import BinanceREST

logger = logging.getLogger(__name__)


def _compute_volatility_range_pct(high: float, low: float, avg: float) -> float:
    """(high - low) / avg * 100. Возвращает 0 если avg == 0."""
    if avg <= 0:
        return 0.0
    return (high - low) / avg * 100


def _ranking_score(ticker: dict, metric: str) -> float:
    """Возвращает число для сортировки в зависимости от выбранной метрики."""
    if metric == "volume":
        try:
            return float(ticker["quoteVolume"])
        except (KeyError, ValueError):
            return 0.0

    if metric == "price_change_abs":
        try:
            return abs(float(ticker["priceChangePercent"]))
        except (KeyError, ValueError):
            return 0.0

    # default & "volatility_range"
    try:
        high = float(ticker["highPrice"])
        low = float(ticker["lowPrice"])
        avg = float(ticker["weightedAvgPrice"])
        return _compute_volatility_range_pct(high, low, avg)
    except (KeyError, ValueError):
        return 0.0


async def get_top_usdt_pairs(
    rest: BinanceREST, n: int = TOP_N_PAIRS
) -> List[str]:
    tickers = await rest.get_24h_tickers()

    candidates = []
    for t in tickers:
        sym = t["symbol"]
        if not sym.endswith("USDT"):
            continue
        if sym in EXCLUDE_SYMBOLS:
            continue

        # Раскладываем все нужные числа один раз — чтобы не дёргать одинаковый
        # парсинг в разных местах
        try:
            quote_volume = float(t["quoteVolume"])
            high = float(t["highPrice"])
            low = float(t["lowPrice"])
            avg = float(t["weightedAvgPrice"])
            change_pct = float(t["priceChangePercent"])
        except (KeyError, ValueError):
            continue

        if quote_volume < MIN_DAILY_VOLUME_USD:
            continue

        vol_range_pct = _compute_volatility_range_pct(high, low, avg)
        if vol_range_pct < MIN_VOLATILITY_RANGE_PCT:
            continue

        candidates.append({
            "symbol": sym,
            "quote_volume": quote_volume,
            "vol_range_pct": vol_range_pct,
            "change_pct": change_pct,
            "ranking_score": _ranking_score(t, RANKING_METRIC),
        })

    candidates.sort(key=lambda x: x["ranking_score"], reverse=True)
    top = candidates[:n]

    logger.info(
        f"Pair selection: ranking_metric='{RANKING_METRIC}', "
        f"min_volume=${MIN_DAILY_VOLUME_USD/1e6:.0f}M, "
        f"min_volatility={MIN_VOLATILITY_RANGE_PCT}% → "
        f"selected {len(top)} pairs"
    )
    # Подробный лог что и почему выбрано
    for c in top[:10]:
        logger.info(
            f"  {c['symbol']:<12} range={c['vol_range_pct']:5.2f}% "
            f"change={c['change_pct']:+6.2f}% "
            f"vol=${c['quote_volume']/1e6:6.1f}M"
        )
    if len(top) > 10:
        logger.info(f"  ... +{len(top)-10} more")

    return [c["symbol"] for c in top]
