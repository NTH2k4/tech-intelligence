import unittest
from unittest.mock import patch

from scripts import run_daily_briefing


def make_article(
    article_id="article-1",
    *,
    recommendation="read",
    status="discovered",
    scored_at="2026-11-06T00:00:00Z",
    delivered_at=None,
    url="https://news.example.com/story",
):
    return {
        "id": article_id,
        "title": "A useful technology update",
        "source": "Example News",
        "url": url,
        "published_at": "2026-11-06T00:00:00Z",
        "score": 82,
        "recommendation": recommendation,
        "status": status,
        "scored_at": scored_at,
        "delivered_at": delivered_at,
        "summary": "A source-backed technical update.",
    }


class EligibilityDiagnosticsTests(unittest.TestCase):
    def test_selector_keeps_only_scored_recommended_undelivered_articles(self):
        state = {
            "articles": [
                make_article("eligible"),
                make_article("skip", recommendation="skip"),
                make_article("unscored", scored_at=None),
                make_article("delivered", status="delivered"),
                make_article("already-sent", delivered_at="2026-11-06T01:00:00Z"),
            ]
        }

        selected = run_daily_briefing.select_eligible_articles(state)

        self.assertEqual([item["id"] for item in selected], ["eligible"])

    def test_exclusion_diagnostics_are_mutually_exclusive_and_counted(self):
        articles = [
            make_article("eligible"),
            make_article("skip", recommendation="skip"),
            make_article("missing-recommendation", recommendation=None),
            make_article("unscored", scored_at=None),
            make_article("delivered", status="delivered"),
            make_article("has-delivered-at", delivered_at="2026-11-06T01:00:00Z"),
            make_article("invalid-url", url="not-a-url"),
            make_article("eligible"),
            None,
        ]

        eligible, counts = run_daily_briefing._collect_eligible_articles(articles)

        self.assertEqual([item["id"] for item in eligible], ["eligible"])
        self.assertEqual(
            counts,
            {
                "recommendation_skip": 1,
                "missing_recommendation": 1,
                "missing_scored_at": 1,
                "already_delivered_status": 1,
                "already_has_delivered_at": 1,
                "synthetic_or_invalid_url": 1,
                "duplicate_id": 1,
                "malformed_record": 1,
            },
        )
        self.assertEqual(len(eligible) + sum(counts.values()), len(articles))

    def test_non_list_state_articles_raise_clear_error(self):
        with self.assertRaisesRegex(RuntimeError, "must be a list"):
            run_daily_briefing.select_eligible_articles({"articles": None})


class ExistingBriefingGuardTests(unittest.TestCase):
    class FakeStateClient:
        def __init__(self, status):
            self.status = status
            self.state_reads = 0

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def get_briefing_status(self, briefing_date):
            self.asserted_date = briefing_date
            return {"ok": True, "briefing": {"status": self.status}}

        def get_state(self, limit=100):
            self.state_reads += 1
            raise AssertionError("Article state must not be read for an existing briefing")

    def test_sent_briefing_skips_generation_and_delivery(self):
        client = self.FakeStateClient("sent")
        with (
            patch.object(run_daily_briefing, "StateAPIClient", return_value=client),
            patch.object(
                run_daily_briefing, "local_briefing_date", return_value="2026-11-06"
            ),
        ):
            result = run_daily_briefing.run(limit=30, send=False)

        self.assertEqual(result, 0)
        self.assertEqual(client.asserted_date, "2026-11-06")
        self.assertEqual(client.state_reads, 0)

    def test_sending_or_failed_briefing_requires_reconciliation(self):
        for status in ("sending", "failed"):
            with self.subTest(status=status):
                client = self.FakeStateClient(status)
                with (
                    patch.object(
                        run_daily_briefing, "StateAPIClient", return_value=client
                    ),
                    patch.object(
                        run_daily_briefing,
                        "local_briefing_date",
                        return_value="2026-11-06",
                    ),
                ):
                    result = run_daily_briefing.run(limit=30, send=False)

                self.assertEqual(result, 2)
                self.assertEqual(client.state_reads, 0)


if __name__ == "__main__":
    unittest.main()
