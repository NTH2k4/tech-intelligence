from __future__ import annotations

import os
import tempfile
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from scripts import preflight_daily_briefing as preflight


class PreflightDailyBriefingTests(unittest.TestCase):
    def run_with_status(self, briefing):
        client = patch.object(preflight, "StateAPIClient")
        mocked_client = client.start()
        self.addCleanup(client.stop)
        mocked_client.return_value.__enter__.return_value.get_briefing_status.return_value = {
            "briefing": briefing
        }

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "github-output"
            with (
                patch.dict(os.environ, {"GITHUB_OUTPUT": str(output)}),
                patch.object(
                    preflight,
                    "briefing_date_now",
                    return_value="2026-11-14",
                ),
                redirect_stderr(StringIO()),
            ):
                code = preflight.main()
            contents = (
                output.read_text(encoding="utf-8")
                if output.exists()
                else ""
            )

        return code, contents

    def test_no_record_allows_pipeline(self):
        code, output = self.run_with_status(None)

        self.assertEqual(code, 0)
        self.assertIn("skip_pipeline=false", output)

    def test_sent_record_skips_pipeline(self):
        code, output = self.run_with_status({"status": "sent"})

        self.assertEqual(code, 0)
        self.assertIn("skip_pipeline=true", output)

    def test_sending_record_fails_closed(self):
        code, output = self.run_with_status({"status": "sending"})

        self.assertEqual(code, 2)
        self.assertEqual(output, "")

    def test_failed_record_fails_closed(self):
        code, output = self.run_with_status({"status": "failed"})

        self.assertEqual(code, 2)
        self.assertEqual(output, "")

    def test_unknown_state_fails_closed(self):
        code, output = self.run_with_status({"status": "unexpected"})

        self.assertEqual(code, 2)
        self.assertEqual(output, "")


if __name__ == "__main__":
    unittest.main()
