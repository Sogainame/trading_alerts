"""
Форматтеры HTML-сообщений для Telegram.
"""
from typing import Optional

from src.alerts.targets import Targets
from src.scoring.engine import ScoringResult


_TIER_BADGES = {
    "PREMIUM": "🔥 <b>PREMIUM</b>",
    "STRONG": "🟢 <b>STRONG</b>",
    "WATCH": "🟡 <b>WATCH</b>",
}

_DIRECTION_RU = {
    "BULLISH": "ВВЕРХ",
    "BEARISH": "ВНИЗ",
}


def format_alert(
    symbol: str,
    result: ScoringResult,
    current_price: float,
    targets: Optional[Targets] = None,
) -> str:
    """
    Главный алерт.
    Содержит:
      1. Шапку (тир, символ, score, направление, цена)
      2. Разбивку по детекторам со вкладами в score
      3. Блок ориентиров (если есть данные стакана) со стопом, целью и RR
    """
    badge = _TIER_BADGES.get(result.tier, "<b>ALERT</b>")
    direction_ru = _DIRECTION_RU.get(result.direction, result.direction)

    lines = [
        f"{badge} • <b>{symbol}</b> • Score {result.score}",
        f"Направление: <b>{direction_ru}</b>",
        f"Цена: <code>{current_price:,.6g}</code>",
        "━━━━━━━━━━━━━━━━━━━━",
    ]
    for s in result.signals:
        lines.append(f"✅ {s.description}  <i>(+{s.score_contribution})</i>")

    # Блок ориентиров — только для bullish сигналов (на споте торгуем только в long)
    if (
        targets is not None
        and result.direction == "BULLISH"
        and (targets.stop_price is not None or targets.target_price is not None)
    ):
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append("📌 <b>ОРИЕНТИРЫ</b>")

        if targets.stop_price is not None:
            lines.append(
                f"🛡 Стоп: <code>{targets.stop_price:,.6g}</code> "
                f"(−{targets.stop_distance_pct:.2f}%, "
                f"стена ${targets.stop_wall_usd/1000:.0f}k)"
            )

        if targets.target_price is not None:
            lines.append(
                f"🎯 Цель: <code>{targets.target_price:,.6g}</code> "
                f"(+{targets.target_distance_pct:.2f}%, "
                f"стена ${targets.target_wall_usd/1000:.0f}k)"
            )

        # RR считается только если есть и стоп и цель
        if targets.stop_price is not None and targets.target_price is not None:
            risk = current_price - targets.stop_price
            reward = targets.target_price - current_price
            if risk > 0:
                rr = reward / risk
                rr_emoji = "🟢" if rr >= 2 else ("🟡" if rr >= 1 else "🔴")
                lines.append(f"{rr_emoji} RR: <b>1:{rr:.2f}</b>")

    return "\n".join(lines)


def format_followup(
    symbol: str, entry_price: float, current_price: float, delay_minutes: int
) -> str:
    change_pct = ((current_price - entry_price) / entry_price) * 100
    if change_pct > 0:
        emoji, sign = "📈", "+"
    elif change_pct < 0:
        emoji, sign = "📉", ""
    else:
        emoji, sign = "➖", ""
    return (
        f"{emoji} <b>{symbol}</b> • +{delay_minutes} мин\n"
        f"Вход: <code>{entry_price:,.6g}</code> → "
        f"Сейчас: <code>{current_price:,.6g}</code>\n"
        f"Изменение: <b>{sign}{change_pct:.2f}%</b>"
    )
