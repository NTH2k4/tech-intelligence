import json
import re
from typing import Any

from integrations.gemini_client import GeminiClient


class BriefingComposer:
    """
    Transform collected news into a Vietnamese technology briefing.
    """

    TELEGRAM_LIMIT = 3800

    def __init__(self, gemini: GeminiClient | None = None):
        self.gemini = gemini or GeminiClient()

    def build_prompt(
        self,
        articles: list[dict[str, Any]],
        demo: bool = False
    ) -> str:
        if not articles:
            raise ValueError("Articles cannot be empty")

        if len(articles) > 30:
            raise ValueError("Maximum 30 articles per briefing")

        data = json.dumps(
            articles,
            ensure_ascii=False,
            indent=2
        )

        demo_notice = ""

        if demo:
            demo_notice = """
IMPORTANT:
This is a DEMONSTRATION using entirely fictional data.
Do not present any article, organization, event or claim
as a real-world fact.

The final briefing MUST begin with:
🧪 BẢN TIN DEMO — DỮ LIỆU GIẢ LẬP
"""

        return f"""
Bạn là chuyên gia phân tích công nghệ và AI,
phụ trách viết bản tin Technology Intelligence bằng tiếng Việt.

NHIỆM VỤ:
Phân tích danh sách bài viết được cung cấp và tạo một
bản tin công nghệ dễ đọc, có chiều sâu và hữu ích.

NGUYÊN TẮC BẮT BUỘC:

1. Chỉ sử dụng thông tin có trong dữ liệu đầu vào.
2. Không bịa đặt sự kiện, số liệu, ngày tháng hoặc phát biểu.
3. Không tự suy diễn tiêu đề thành nội dung đã được xác nhận.
4. Phân biệt thông tin chính thức với nhận định cộng đồng.
5. Luôn giữ nguyên URL nguồn.
6. Nếu thiếu thông tin, phải nói rõ giới hạn.
7. Không tạo tin tức mới ngoài danh sách đầu vào.
8. Ưu tiên các nội dung có tác động thực tế đến ngành công nghệ.

CẤU TRÚC BẢN TIN:

TECH MORNING BRIEF

📌 TỔNG QUAN
Tóm tắt những chủ đề nổi bật nhất.

🔥 TIN ĐÁNG CHÚ Ý
Chọn tối đa 5 tin quan trọng.
Với mỗi tin:
- Tiêu đề.
- Tóm tắt.
- Điểm mới đáng chú ý.
- Tác động hoặc ứng dụng thực tế nếu dữ liệu hỗ trợ.
- Nguồn và URL.

💻 DEVELOPER RADAR
Những thông tin hữu ích cho developer, backend và AI-driven development.

💡 ĐỀ XUẤT HÔM NAY
Chỉ đưa ra một đề xuất thực hành khi dữ liệu
thực sự hỗ trợ một đề xuất hữu ích.

YÊU CẦU TRÌNH BÀY:

- Viết bằng tiếng Việt tự nhiên.
- Dùng tiêu đề ngắn và bullet points.
- Không sử dụng bảng.
- Không dùng Markdown table.
- Không viết lời chào dài dòng.
- Ưu tiên thông tin cô đọng.
- Nội dung phù hợp để đọc trên Telegram.
- Độ dài tối đa khoảng 3500 ký tự.

{demo_notice}

DỮ LIỆU ĐẦU VÀO:

{data}

Hãy tạo bản tin ngay bây giờ.
"""

    def compose(
        self,
        articles: list[dict[str, Any]],
        demo: bool = False
    ) -> str:
        # URLs are deliberately withheld from Gemini. Source links are rendered
        # below from the immutable selected article records.
        prompt_articles = [
            {key: value for key, value in article.items() if key != "url"}
            for article in articles
        ]
        prompt = self.build_prompt(prompt_articles, demo)

        result = self.gemini.generate(prompt)

        if not result or not result.strip():
            raise RuntimeError("Briefing generation returned empty content")

        result = result.strip()

        if demo:
            prefix = "🧪 BẢN TIN DEMO — DỮ LIỆU GIẢ LẬP"

            if not result.startswith(prefix):
                result = f"{prefix}\n\n{result}"

        # Strip any URL Gemini may have invented or reconstructed. The only
        # URLs sent downstream are appended directly from article records.
        result = re.sub(r"https?://\S+", "", result)
        result = re.sub(r"www\.\S+", "", result).rstrip()
        links = "\n".join(
            f"- {article.get('source') or article.get('title')}: {article['url']}"
            for article in articles
            if isinstance(article.get("url"), str) and article["url"].strip()
        )
        return f"{result}\n\n🔗 NGUỒN\n{links}" if links else result

    @classmethod
    def split_message(
        cls,
        message: str
    ) -> list[str]:
        """
        Split long text without exceeding Telegram's message limit.
        Prefer paragraph and word boundaries.
        """

        if not message:
            return []

        chunks = []
        remaining = message.strip()

        while len(remaining) > cls.TELEGRAM_LIMIT:
            split_at = remaining.rfind(
                "\n",
                0,
                cls.TELEGRAM_LIMIT
            )

            if split_at < cls.TELEGRAM_LIMIT // 2:
                split_at = remaining.rfind(
                    " ",
                    0,
                    cls.TELEGRAM_LIMIT
                )

            if split_at <= 0:
                split_at = cls.TELEGRAM_LIMIT

            chunks.append(remaining[:split_at].strip())
            remaining = remaining[split_at:].strip()

        if remaining:
            chunks.append(remaining)

        return chunks

    def send(
        self,
        message: str,
        telegram_client
    ) -> list[dict]:
        chunks = self.split_message(message)

        if not chunks:
            raise ValueError("Cannot send an empty briefing")

        results = []

        for chunk in chunks:
            result = telegram_client.send_message(chunk)
            results.append(result)

        return results
