"""
Telegram нотифаер через REST Bot API (httpx async).
"""
import logging
from typing import Optional

import httpx

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(
        self,
        token: Optional[str] = TELEGRAM_BOT_TOKEN,
        chat_id: Optional[str] = TELEGRAM_CHAT_ID,
    ):
        if not token or not chat_id:
            raise ValueError("TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID должны быть в .env")
        self.token = token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{token}/sendMessage"
        self._client = httpx.AsyncClient(timeout=10.0)

    async def send(
        self, text: str, reply_to: Optional[int] = None
    ) -> Optional[dict]:
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if reply_to is not None:
            payload["reply_to_message_id"] = reply_to
            payload["allow_sending_without_reply"] = True
        try:
            resp = await self._client.post(self.api_url, json=payload)
            if resp.status_code != 200:
                logger.error(f"Telegram API error {resp.status_code}: {resp.text}")
                return None
            return resp.json().get("result")
        except Exception as e:
            logger.exception(f"Telegram send failed: {e}")
            return None

    async def close(self) -> None:
        await self._client.aclose()
