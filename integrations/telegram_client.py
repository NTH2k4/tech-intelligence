import os

import httpx
from dotenv import load_dotenv


load_dotenv()


class TelegramClient:
    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")

        if not self.token:
            raise RuntimeError(
                "TELEGRAM_BOT_TOKEN is not configured"
            )

        if not self.chat_id:
            raise RuntimeError(
                "TELEGRAM_CHAT_ID is not configured"
            )

        self.api_url = (
            f"https://api.telegram.org/bot{self.token}"
        )

    def send_message(self, text: str) -> dict:
        if not text or not text.strip():
            raise ValueError("Message cannot be empty")

        if len(text) > 4096:
            raise ValueError(
                "Message exceeds Telegram's 4096-character limit"
            )

        try:
            response = httpx.post(
                f"{self.api_url}/sendMessage",
                json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "link_preview_options": {
                        "is_disabled": True
                    }
                },
                timeout=20
            )

            response.raise_for_status()

            result = response.json()

            if not result.get("ok"):
                raise RuntimeError(
                    result.get("description", "Send failed")
                )

            return result["result"]

        except httpx.HTTPError as exc:
            raise RuntimeError(
                f"Telegram request failed: {type(exc).__name__}"
            ) from exc
