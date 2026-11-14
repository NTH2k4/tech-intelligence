"""Fail-closed preflight for unattended daily briefing runs.

The D1 date-level record is authoritative. A sent briefing skips the expensive
pipeline; an in-progress or failed record stops the run for manual reconciliation.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from integrations.state_api_client import StateAPIClient


TIME_ZONE = ZoneInfo("Asia/Ho_Chi_Minh")


def briefing_date_now() -> str:
    return datetime.now(TIME_ZONE).date().isoformat()


def write_output(name: str, value: str) -> None:
    output_path = os.getenv("GITHUB_OUTPUT")
    if output_path:
        with Path(output_path).open("a", encoding="utf-8") as output:
            output.write(f"{name}={value}\n")


def main() -> int:
    date = briefing_date_now()
    print(f"Checking delivery state for Vietnam date {date}...")

    with StateAPIClient() as client:
        response = client.get_briefing_status(date)

    briefing = response.get("briefing")
    if briefing is None:
        write_output("skip_pipeline", "false")
        print("No briefing record exists for today. Pipeline may proceed.")
        return 0

    status = str(briefing.get("status") or "").lower()
    print(f"Existing briefing record found for {date}: status={status or 'unknown'}.")

    if status == "sent":
        write_output("skip_pipeline", "true")
        print(
            "ALREADY SENT: today's briefing is confirmed in State API. "
            "Skipping collection, scoring, and Telegram delivery."
        )
        return 0

    if status == "sending":
        print(
            "DELIVERY IN PROGRESS: refusing another run. Reconcile Telegram "
            "messages and State API before any retry.",
            file=sys.stderr,
        )
        return 2

    if status == "failed":
        print(
            "PREVIOUS DELIVERY FAILED: refusing an automatic retry because "
            "partial Telegram delivery may have occurred. Reconcile first.",
            file=sys.stderr,
        )
        return 2

    print(
        f"Unexpected briefing state {status!r}; refusing to run fail-open.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
