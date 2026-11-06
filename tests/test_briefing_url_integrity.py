import re
import unittest
from unittest.mock import patch

from briefing.composer import BriefingComposer
from integrations.state_api_client import APPLICATION_USER_AGENT, StateAPIClient
from scripts import run_daily_briefing


class FakeGemini:
    def __init__(self, output):
        self.output = output
        self.prompt = None

    def generate(self, prompt):
        self.prompt = prompt
        return self.output


def article(url, title="Source title", source="Source"):
    return {"id": title, "title": title, "source": source, "url": url,
            "summary": "The source reports a limited technical update."}


class BriefingURLIntegrityTests(unittest.TestCase):
    def test_exact_url_preserved_and_not_given_to_model(self):
        original = "https://github.com/org/project?tab=readme#top"
        gemini = FakeGemini("TECH MORNING BRIEF\n📌 TỔNG QUAN\nBản cập nhật kỹ thuật.")
        result = BriefingComposer(gemini).compose([article(original)])
        self.assertIn(original, result)
        self.assertNotIn(original, gemini.prompt)

    def test_github_org_tampering_and_invented_urls_are_removed(self):
        gemini = FakeGemini("Tin mới https://github.org/org/project và https://fake.invalid/story")
        result = BriefingComposer(gemini).compose([article("https://github.com/org/project")])
        self.assertNotIn("github.org", result)
        self.assertNotIn("fake.invalid", result)
        self.assertIn("https://github.com/org/project", result)

    def test_multiple_sources_are_rendered_from_records(self):
        records = [article("https://a.example/story", "A", "Alpha"),
                   article("https://b.example/story", "B", "Beta")]
        result = BriefingComposer(FakeGemini("Tóm tắt dựa trên nội dung nguồn.")).compose(records)
        self.assertIn("Alpha: https://a.example/story", result)
        self.assertIn("Beta: https://b.example/story", result)

    def test_all_chunks_contain_only_record_urls(self):
        url = "https://github.com/org/project"
        prose = "Tin kỹ thuật. " * 700
        result = BriefingComposer(FakeGemini(prose + " https://github.org/wrong")).compose([article(url)])
        chunks = BriefingComposer.split_message(result)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= BriefingComposer.TELEGRAM_LIMIT for chunk in chunks))
        self.assertEqual(re.findall(r"https?://\S+", "\n".join(chunks)), [url])

    def test_empty_and_missing_source_urls_do_not_create_links(self):
        records = [article(""), {"id": "missing", "title": "No URL", "source": "None"}]
        result = BriefingComposer(FakeGemini("Tóm tắt ngắn.")).compose(records)
        self.assertNotIn("🔗 NGUỒN", result)
        self.assertNotRegex(result, r"https?://")

    def test_prompt_does_not_ask_gemini_to_print_urls(self):
        gemini = FakeGemini("Tóm tắt ngắn.")
        BriefingComposer(gemini).compose([article("https://source.example/story")])
        self.assertIn("KHÔNG viết, nhắc lại, suy đoán hoặc tạo URL", gemini.prompt)
        self.assertIn("URL sẽ được hệ thống tự động đính kèm", gemini.prompt)


    def test_prompt_requires_precise_claim_status_and_no_unsupported_upgrades(self):
        gemini = FakeGemini("Tóm tắt ngắn.")
        BriefingComposer(gemini).compose([article("https://source.example/story")])
        self.assertIn("đề xuất bản vá", gemini.prompt)
        self.assertIn("đã phát hành", gemini.prompt)
        self.assertIn("không suy diễn chi tiết kỹ thuật", gemini.prompt)
        self.assertIn("Giữ nguyên điều kiện, phạm vi và giới hạn", gemini.prompt)

    def test_url_placeholders_and_empty_metadata_are_cleaned(self):
        output = (
            "Tin đáng chú ý\n"
            "- Nguồn & URL: Nguồn: OpenAI. URL chi tiết: Không có trong dữ liệu đầu vào.\n"
            "- Mã nguồn/Dữ liệu: \n"
            "- URL nguồn: Không có trong dữ liệu đầu vào"
        )
        result = BriefingComposer(FakeGemini(output)).compose(
            [article("https://openai.com/index/example", source="OpenAI")]
        )
        self.assertIn("- Nguồn: OpenAI", result)
        self.assertNotIn("URL chi tiết", result)
        self.assertNotIn("Không có trong dữ liệu đầu vào", result)
        self.assertNotIn("Mã nguồn/Dữ liệu:", result)
        self.assertIn("https://openai.com/index/example", result)


class DeliveryConfirmationTests(unittest.TestCase):
    def test_noninteractive_send_requires_explicit_yes(self):
        with patch.object(run_daily_briefing.sys.stdin, "isatty", return_value=False):
            self.assertEqual(run_daily_briefing._delivery_confirmation(send=True, yes=False),
                             "noninteractive_confirmation_required")
            self.assertIsNone(run_daily_briefing._delivery_confirmation(send=True, yes=True))

    def test_preview_never_authorizes_delivery(self):
        with patch.object(run_daily_briefing.sys.stdin, "isatty", return_value=False):
            self.assertIsNone(run_daily_briefing._delivery_confirmation(send=False, yes=False))
            self.assertEqual(run_daily_briefing._delivery_confirmation(send=False, yes=True),
                             "yes_requires_send")


class StateAPIUserAgentTests(unittest.TestCase):
    def test_client_sets_descriptive_application_user_agent(self):
        client = StateAPIClient(base_url="https://state.example", token="test-token")
        try:
            self.assertEqual(
                client.http.headers.get("user-agent"), APPLICATION_USER_AGENT
            )
        finally:
            client.close()


if __name__ == "__main__":
    unittest.main()
