"""
Отправка алертов в Telegram через REST Bot API.
Используем httpx async — лёгкий и не тащим тяжёлый python-telegram-bot framework.
"""
import logging
from typing import List

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

    async def send(self, text: str) -> bool:
        try:
            resp = await self._client.post(
                self.api_url,
                json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
            )
            if resp.status_code != 200:
                logger.error(f"Telegram API error {resp.status_code}: {resp.text}")
                return False
            return True
        except Exception as e:
            logger.exception(f"Failed to send Telegram message: {e}")
            return False

    async def close(self) -> None:
        await self._client.aclose()


def format_alert(symbol: str, signals: List[dict], timeframe: str) -> str:
    """
    Формирует HTML-строку для Telegram.
    Все сигналы в одном алерте должны быть однонаправленные (фильтруется в scanner.py).
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
