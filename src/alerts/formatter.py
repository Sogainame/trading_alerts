"""
Форматтеры HTML-сообщений для Telegram.
"""
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


def format_alert(symbol: str, result: ScoringResult, current_price: float) -> str:
    """
    Главный алерт. Содержит разбивку по сработавшим детекторам — ты сразу видишь
    *почему* алерт пришёл, какие именно факторы сработали.
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
