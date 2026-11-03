import os
import sys

import httpx
from dotenv import load_dotenv


load_dotenv()


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")

    if not token:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN is not configured"
        )

    url = f"https://api.telegram.org/bot{token}/getUpdates"

    try:
        response = httpx.get(url, timeout=20)
        response.raise_for_status()
        data = response.json()

        if not data.get("ok"):
            raise RuntimeError(
                data.get("description", "Telegram API error")
            )
            
        chat_ids = set()

        for update in data.get("result", []):
            message = (
                update.get("message")
                or update.get("edited_message")
                or update.get("channel_post")
            )

            if message and message.get("chat"):
                chat_ids.add(
                    str(message["chat"]["id"])
                )

        if not chat_ids:
            print(
                "No chat found. Send /start and a message "
                "to your bot, then run this script again."
            )
            return

        print("Detected Chat IDs:")

        for chat_id in sorted(chat_ids):
            print(chat_id)

    except httpx.HTTPError as exc:
        print(
            f"Telegram connection failed: {type(exc).__name__}",
            file=sys.stderr
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
