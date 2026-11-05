import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_scheduled_pipeline.sh"
REQUIRED = {
    "STATE_API_URL": "https://state.example",
    "STATE_API_TOKEN": "test-token",
    "GEMINI_API_KEY": "test-key",
    "GEMINI_MODEL": "briefing-model",
    "GEMINI_SCORING_MODEL": "scoring-model",
    "TELEGRAM_BOT_TOKEN": "test-bot-token",
    "TELEGRAM_CHAT_ID": "test-chat",
}


class ScheduledEntrypointTests(unittest.TestCase):
    def test_missing_secret_fails_before_pipeline(self):
        env = {"PATH": os.environ["PATH"]}
        result = subprocess.run(
            ["bash", str(SCRIPT)], cwd=ROOT, env=env, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("STATE_API_URL is required", result.stderr)

    def test_default_and_preview_run_ingestion_without_delivery_flags(self):
        with tempfile.TemporaryDirectory() as temp:
            bin_dir = Path(temp) / "bin"
            bin_dir.mkdir()
            log = Path(temp) / "invocations"
            fake_python = bin_dir / "python"
            fake_python.write_text(
                "#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$INVOCATION_LOG\"\n"
            )
            fake_python.chmod(0o755)
            env = {**os.environ, **REQUIRED, "INVOCATION_LOG": str(log)}
            env["PATH"] = f"{bin_dir}:{env['PATH']}"
            result = subprocess.run(
                ["bash", str(SCRIPT), "--preview"], cwd=ROOT, env=env, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            calls = log.read_text().splitlines()
            self.assertEqual(len(calls), 2)
            self.assertIn("scripts.run_pipeline", calls[0])
            self.assertIn("scripts.run_daily_briefing", calls[1])
            self.assertNotIn("--send", calls[1])
            self.assertNotIn("--yes", calls[1])

    def test_send_mode_explicitly_authorizes_unattended_delivery(self):
        with tempfile.TemporaryDirectory() as temp:
            bin_dir = Path(temp) / "bin"
            bin_dir.mkdir()
            log = Path(temp) / "invocations"
            fake_python = bin_dir / "python"
            fake_python.write_text(
                "#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$INVOCATION_LOG\"\n"
            )
            fake_python.chmod(0o755)
            env = {**os.environ, **REQUIRED, "INVOCATION_LOG": str(log)}
            env["PATH"] = f"{bin_dir}:{env['PATH']}"
            result = subprocess.run(
                ["bash", str(SCRIPT), "--send"], cwd=ROOT, env=env, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            calls = log.read_text().splitlines()
            self.assertEqual(len(calls), 2)
            self.assertIn("--send", calls[1])
            self.assertIn("--yes", calls[1])

    def test_rejects_non_https_state_api_url(self):
        env = {**os.environ, **REQUIRED, "STATE_API_URL": "http://state.example"}
        result = subprocess.run(
            ["bash", str(SCRIPT)], cwd=ROOT, env=env, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("must use HTTPS", result.stderr)

    def test_preview_does_not_require_telegram_credentials(self):
        with tempfile.TemporaryDirectory() as temp:
            bin_dir = Path(temp) / "bin"
            bin_dir.mkdir()
            log = Path(temp) / "invocations"
            fake_python = bin_dir / "python"
            fake_python.write_text(
                "#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$INVOCATION_LOG\"\n"
            )
            fake_python.chmod(0o755)
            env = {**os.environ, **REQUIRED, "INVOCATION_LOG": str(log)}
            env.pop("TELEGRAM_BOT_TOKEN")
            env.pop("TELEGRAM_CHAT_ID")
            env["PATH"] = f"{bin_dir}:{env['PATH']}"
            result = subprocess.run(
                ["bash", str(SCRIPT), "--preview"], cwd=ROOT, env=env, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
