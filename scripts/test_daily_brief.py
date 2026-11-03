import argparse

from briefing.composer import BriefingComposer
from integrations.telegram_client import TelegramClient


DEMO_ARTICLES = [
    {
        "id": "demo-001",
        "title": "Minh họa: Công cụ AI hỗ trợ kiểm thử API phiên bản 0.1",
        "source": "Demo Technology Lab",
        "url": "https://example.com/demo/ai-api-testing",
        "category": "AI Development",
        "published_at": "2026-11-03T01:00:00Z",
        "score": 85,
        "summary": (
            "Dữ liệu giả lập: một công cụ minh họa sử dụng "
            "AI để đề xuất các trường hợp kiểm thử API "
            "dựa trên mô tả endpoint."
        )
    },
    {
        "id": "demo-002",
        "title": "Minh họa: Thư viện Python mới cho tự động hóa workflow",
        "source": "Demo Developer News",
        "url": "https://example.com/demo/python-workflow",
        "category": "Developer Tools",
        "published_at": "2026-11-03T02:00:00Z",
        "score": 75,
        "summary": (
            "Dữ liệu giả lập: thư viện minh họa hỗ trợ "
            "quản lý tác vụ, retry và xử lý lỗi trong "
            "những workflow tự động."
        )
    },
    {
        "id": "demo-003",
        "title": "Minh họa: Kiến trúc serverless cho ứng dụng AI Agent",
        "source": "Demo Cloud Engineering",
        "url": "https://example.com/demo/serverless-agent",
        "category": "Cloud Infrastructure",
        "published_at": "2026-11-03T03:00:00Z",
        "score": 80,
        "summary": (
            "Dữ liệu giả lập: ví dụ kiến trúc sử dụng "
            "scheduled jobs, database serverless và "
            "API để chạy những tác vụ AI theo lịch."
        )
    }
]


def main():
    parser = argparse.ArgumentParser(
        description="Test AI Technology Briefing"
    )

    parser.add_argument(
        "--send",
        action="store_true",
        help="Send generated briefing to Telegram"
    )

    args = parser.parse_args()

    print("Initializing Briefing Composer...")

    composer = BriefingComposer()

    print("Generating demo briefing...")

    briefing = composer.compose(
        articles=DEMO_ARTICLES,
        demo=True
    )

    print("\n========== GENERATED BRIEFING ==========\n")
    print(briefing)
    print("\n========================================\n")

    if not args.send:
        print("Preview mode: message was NOT sent.")
        print("Run with --send to deliver it to Telegram.")
        return

    print("Connecting to Telegram...")

    telegram = TelegramClient()

    results = composer.send(
        message=briefing,
        telegram_client=telegram
    )

    print("Briefing sent successfully!")

    for result in results:
        print(
            f"Telegram message ID: {result['message_id']}"
        )


if __name__ == "__main__":
    main()
