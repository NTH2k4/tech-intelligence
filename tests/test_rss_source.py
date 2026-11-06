import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from collector.sources.rss import (
    MAX_SUMMARY_LENGTH,
    _extract_best_summary,
    fetch_rss_source,
)


class RSSSummaryExtractionTests(unittest.TestCase):
    def test_prefers_longer_cleaned_content_over_short_summary(self):
        entry = {
            "summary": "<p>Short description.</p>",
            "content": [
                {
                    "type": "text/html",
                    "value": (
                        "<p>Full article content includes the architecture, "
                        "implementation details, benchmarks, and limitations.</p>"
                    ),
                }
            ],
        }

        result = _extract_best_summary(entry)

        self.assertIn("implementation details", result)
        self.assertNotIn("<p>", result)
        self.assertGreater(len(result), len("Short description."))

    def test_summary_is_used_when_content_is_missing_or_empty(self):
        self.assertEqual(
            _extract_best_summary({"summary": "<p>Useful summary.</p>"}),
            "Useful summary.",
        )
        self.assertEqual(
            _extract_best_summary(
                {"summary": "Useful summary.", "content": []}
            ),
            "Useful summary.",
        )

    def test_longest_valid_content_candidate_is_selected(self):
        entry = {
            "summary": "Short summary",
            "content": [
                {"value": "Medium-length source text."},
                {"value": "<div>The longest and most detailed source content.</div>"},
                {"value": None},
                "malformed content item",
            ],
        }

        self.assertEqual(
            _extract_best_summary(entry),
            "The longest and most detailed source content.",
        )

    def test_selected_text_is_bounded_to_normalizer_limit(self):
        entry = {
            "summary": "A" * (MAX_SUMMARY_LENGTH + 500),
            "content": [{"value": "B" * (MAX_SUMMARY_LENGTH + 1000)}],
        }

        result = _extract_best_summary(entry)

        self.assertEqual(len(result), MAX_SUMMARY_LENGTH)
        self.assertEqual(result, "B" * MAX_SUMMARY_LENGTH)

    def test_empty_or_non_text_candidates_return_empty_string(self):
        self.assertEqual(
            _extract_best_summary(
                {"summary": None, "content": [{"value": None}, 123]}
            ),
            "",
        )


class RSSCollectorIntegrationTests(unittest.TestCase):
    @patch("collector.sources.rss.feedparser.parse")
    def test_collector_persists_richer_content_in_article_summary(self, parse_feed):
        parse_feed.return_value = SimpleNamespace(
            bozo=False,
            entries=[
                {
                    "title": "A technical announcement",
                    "link": "https://news.example.com/announcement",
                    "summary": "<p>Short abstract.</p>",
                    "content": [
                        {
                            "value": (
                                "<p>Detailed announcement with API changes, "
                                "compatibility information, and migration notes.</p>"
                            )
                        }
                    ],
                }
            ],
        )

        response = Mock()
        response.content = b"<rss/>"
        client = Mock()
        client.get.return_value = response
        source = {
            "id": "example",
            "name": "Example News",
            "category": "Developer Tools",
            "url": "https://news.example.com/feed.xml",
            "max_items": 8,
        }

        articles = fetch_rss_source(client, source)

        self.assertEqual(len(articles), 1)
        self.assertIn("migration notes", articles[0]["summary"])
        self.assertNotIn("<p>", articles[0]["summary"])
        self.assertEqual(articles[0]["source_id"], "example")
        client.get.assert_called_once_with(source["url"])
        response.raise_for_status.assert_called_once()


if __name__ == "__main__":
    unittest.main()
