"""
Отправка алертов в Telegram через REST Bot API.
Используем httpx async — лёгкий и не тащим тяжёлый python-telegram-bot framework.
"""
import logging
from typing import List, Optional

import httpx

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, token: str = TELEGRAM_BOT_TOKEN, chat_id: str = TELEGRAM_CHAT_ID):
        if not token or not chat_id:
            raise ValueError(
                "TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID должны быть прописаны в .env"
            )
        self.token = token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{token}/sendMessage"
        self._client = httpx.AsyncClient(timeout=10.0)

    async def send(self, text: str, reply_to: Optional[int] = None) -> Optional[dict]:
        """
        Отправить сообщение. Возвращает result dict из Telegram API
        (содержит message_id для последующих reply) или None при ошибке.

        Если передан reply_to — сообщение будет ответом на сообщение с этим id.
        """
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if reply_to is not None:
            payload["reply_to_message_id"] = reply_to
            # Если оригинальное сообщение удалено — всё равно отправим, без ошибки
            payload["allow_sending_without_reply"] = True

        try:
            resp = await self._client.post(self.api_url, json=payload)
            if resp.status_code != 200:
                logger.error(f"Telegram API error {resp.status_code}: {resp.text}")
                return None
            data = resp.json()
            return data.get("result")
        except Exception as e:
            logger.exception(f"Failed to send Telegram message: {e}")
            return None

    async def close(self) -> None:
        await self._client.aclose()


def format_alert(symbol: str, signals: List[dict], timeframe: str) -> str:
    """
    HTML-строка для основного алерта.
    Все сигналы должны быть однонаправленными (фильтруется в scanner.py).
    """
    pattern_names = {
        "VOLUME_SPIKE": "Volume Spike",
        "ENGULFING": "Engulfing",
    }
    direction_emoji = {"BULLISH": "🟢", "BEARISH": "🔴"}

    first = signals[0]
    direction = first["direction"]
    price = first["price"]
    vol_mult = max(s["volume_multiplier"] for s in signals)

    pattern_str = " + ".join(
        pattern_names.get(s["pattern"], s["pattern"]) for s in signals
    )

    emoji = direction_emoji.get(direction, "")
    direction_ru = "ВВЕРХ" if direction == "BULLISH" else "ВНИЗ"

    return (
        f"🚨 <b>{symbol}</b> • {timeframe}\n"
        f"{emoji} <b>{direction_ru}</b> • {pattern_str}\n"
        f"💰 Цена: <code>{price:,.6g}</code>\n"
        f"📊 Объём: <b>{vol_mult:.1f}x</b> от среднего"
    )


def format_followup(
    symbol: str, entry_price: float, current_price: float, delay_minutes: int
) -> str:
    """
    HTML-строка для follow-up через N минут после алерта.
    Отправляется reply'ем на исходный алерт.
    """
    change_pct = ((current_price - entry_price) / entry_price) * 100

    if change_pct > 0:
        emoji = "📈"
        sign = "+"
    elif change_pct < 0:
        emoji = "📉"
        sign = ""
    else:
        emoji = "➖"
        sign = ""

    return (
        f"{emoji} <b>{symbol}</b> • +{delay_minutes} мин\n"
        f"Вход: <code>{entry_price:,.6g}</code> → "
        f"Сейчас: <code>{current_price:,.6g}</code>\n"
        f"Изменение: <b>{sign}{change_pct:.2f}%</b>"
    )
