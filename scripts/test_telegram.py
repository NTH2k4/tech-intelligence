from datetime import datetime, timezone

from integrations.telegram_client import TelegramClient


def main():
    telegram = TelegramClient()

    now = datetime.now(timezone.utc).strftime(
        "%Y-%m-%d %H:%M UTC"
    )

    message = f"""
🚀 TECH INTELLIGENCE

Telegram integration test successful!

Time: {now}

Your personal technology intelligence
system is now connected to Telegram.

Next step:
Integrate Gemini and the automated news collector.

#TechIntelligence #AI
""".strip()

    result = telegram.send_message(message)

    print("Telegram message sent successfully!")
    print(f"Message ID: {result['message_id']}")


if __name__ == "__main__":
    main()
