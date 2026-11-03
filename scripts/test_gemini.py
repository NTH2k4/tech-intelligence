from integrations.gemini_client import GeminiClient


def main():
    gemini = GeminiClient()

    prompt = """
    Bạn là trợ lý nghiên cứu công nghệ.

    Hãy trả lời bằng tiếng Việt:

    1. AI Agent là gì?
    2. Khác biệt giữa AI Agent và chatbot thông thường?
    3. Cho một ví dụ ứng dụng AI Agent trong phát triển backend.

    Trả lời ngắn gọn, có cấu trúc.
    """

    print("Connecting to Gemini...")
    print(f"Model: {gemini.model}")

    response = gemini.generate(prompt)

    print("\n========== GEMINI RESPONSE ==========\n")
    print(response)
    print("\n=====================================")


if __name__ == "__main__":
    main()
