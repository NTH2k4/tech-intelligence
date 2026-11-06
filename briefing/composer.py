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
5. Bảo toàn chính xác trạng thái và mức độ chắc chắn của thông tin nguồn: phát hiện, nghi vấn, xác thực, khai thác thử nghiệm, báo cáo, bản vá ứng viên được tạo, bản vá được maintainer chấp nhận/hợp nhất và bản vá đã phát hành là các trạng thái khác nhau. Bản vá do AI tạo ra không có nghĩa là lỗ hổng đã được sửa hoặc bản vá đã được upstream. Với tin an ninh, phải gắn từng con số với đúng đối tượng: phát hiện ứng viên, lỗ hổng đã tái hiện, PoC/exploit, bản vá được tạo và bản vá đã được upstream; không gộp hoặc đánh tráo các số liệu này. Chỉ nói lỗ hổng đã được khắc phục khi nguồn xác nhận rõ trạng thái triển khai.
6. Không phóng đại số liệu hoặc kết quả: phân biệt ứng viên, thử nghiệm, kết quả đã xác thực và kết quả triển khai thực tế. Giữ nguyên điều kiện, phạm vi và giới hạn quan trọng đi kèm con số.
7. Mô tả đúng loại tác vụ và phương thức của sản phẩm/mô hình. Với tính năng video, bắt buộc phân biệt: (a) tạo/sinh video; (b) chỉnh sửa video; (c) hiểu/phân tích nội dung video đầu vào. Việc mô hình tạo hoặc chỉnh sửa clip KHÔNG chứng minh mô hình có khả năng hiểu, tóm tắt, nhận diện hoặc phân tích video do người dùng tải lên. Phân biệt thời lượng video ĐƯỢC TẠO (đầu ra) với độ dài video ĐẦU VÀO được hỗ trợ; không diễn giải "tạo video dài đến 15 giây" thành "xử lý/hiểu video đầu vào dài 15 giây". Chỉ nêu đúng năng lực được nguồn công bố.
8. Khi dữ liệu đầu vào chỉ có tiêu đề và tóm tắt ngắn, không suy diễn chi tiết kỹ thuật vượt quá những gì được nêu. Nếu chưa đủ căn cứ, hãy diễn đạt thận trọng hoặc bỏ chi tiết đó.
9. KHÔNG viết, nhắc lại, suy đoán hoặc tạo URL trong nội dung bản tin. URL sẽ được hệ thống tự động đính kèm chính xác ở mục NGUỒN.
10. Nếu thiếu thông tin, phải nói rõ giới hạn.
11. Không tạo tin tức mới ngoài danh sách đầu vào.
12. Ưu tiên các nội dung có tác động thực tế đến ngành công nghệ.

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
- Tên nguồn (chỉ ghi tên nguồn, KHÔNG ghi URL; hệ thống sẽ tự đính kèm liên kết ở cuối bản tin).

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
- Không viết các nhãn như "URL chi tiết", "URL nguồn", "Mã nguồn/Dữ liệu" nếu dữ liệu không cung cấp giá trị tương ứng.
- Không viết câu kiểu "Không có trong dữ liệu đầu vào" để giải thích việc thiếu URL; hệ thống tự đính kèm URL ở mục NGUỒN.
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
        result = re.sub(r"www\.\S+", "", result)

        # Gemini may emit placeholders because URLs are deliberately withheld.
        # Preserve the source name while removing misleading/empty URL fields.
        cleaned_lines = []
        for line in result.splitlines():
            source_line = re.match(
                r"^(\s*[-•]\s*)?Nguồn\s*&\s*URL\s*:\s*Nguồn\s*:\s*(.*?)(?:[.;]\s*URL(?:\s+chi\s+tiết)?\s*:.*)?$",
                line,
                flags=re.IGNORECASE,
            )
            if source_line:
                source_name = source_line.group(2).strip().rstrip(".;")
                if source_name:
                    prefix = source_line.group(1) or "- "
                    cleaned_lines.append(f"{prefix}Nguồn: {source_name}")
                continue

            if re.match(
                r"^\s*[-•]\s*(?:Mã\s*nguồn(?:/Dữ\s*liệu)?|Dữ\s*liệu)\s*:\s*$",
                line,
                flags=re.IGNORECASE,
            ):
                continue

            line = re.sub(
                r"\s*URL(?:\s+chi\s+tiết|\s+nguồn)?\s*:\s*(?:Không\s+có\s+trong\s+dữ\s+liệu\s+đầu\s+vào)?\.?\s*$",
                "",
                line,
                flags=re.IGNORECASE,
            )
            cleaned_lines.append(line)

        result = "\n".join(cleaned_lines).strip()
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
