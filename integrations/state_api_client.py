import os
from pathlib import Path
from typing import Any

import httpx
from dotenv import dotenv_values, load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]

load_dotenv(PROJECT_ROOT / ".env")


class StateAPIError(RuntimeError):
    """Raised when the Tech Intelligence State API request fails."""


class StateAPIClient:
    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        timeout: float = 30.0,
    ):
        self.base_url = (
            base_url or os.getenv("STATE_API_URL", "")
        ).strip().rstrip("/")

        if not self.base_url:
            raise StateAPIError("STATE_API_URL is not configured")

        if not self.base_url.startswith(("http://", "https://")):
            raise StateAPIError("STATE_API_URL must use HTTP or HTTPS")

        self.token = token or os.getenv("STATE_API_TOKEN")

        # Local development fallback:
        # Reuse the Worker token without copying it into Python .env.
        if not self.token:
            dev_vars_path = (
                PROJECT_ROOT
                / "cloudflare"
                / "state-api"
                / ".dev.vars"
            )

            if dev_vars_path.exists():
                local_secrets = dotenv_values(dev_vars_path)
                self.token = local_secrets.get("API_BEARER_TOKEN")

        if not self.token:
            raise StateAPIError(
                "State API token is not configured. "
                "Set STATE_API_TOKEN or configure Worker .dev.vars."
            )

        self.http = httpx.Client(
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def close(self):
        self.http.close()

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict:
        try:
            response = self.http.request(
                method=method,
                url=f"{self.base_url}{path}",
                params=params,
                json=payload,
            )
        except httpx.TimeoutException as exc:
            raise StateAPIError(
                "State API request timed out"
            ) from exc
        except httpx.RequestError as exc:
            raise StateAPIError(
                f"State API connection failed: {type(exc).__name__}"
            ) from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise StateAPIError(
                f"State API returned invalid JSON (HTTP {response.status_code})"
            ) from exc

        if not isinstance(data, dict):
            raise StateAPIError("State API response must be a JSON object")

        if not response.is_success:
            error_code = data.get("error", "request_failed")
            raise StateAPIError(
                f"State API returned HTTP {response.status_code}: {error_code}"
            )

        if data.get("ok") is not True:
            error_code = data.get("error", "unknown_api_error")
            raise StateAPIError(
                f"State API operation failed: {error_code}"
            )

        return data

    def get_state(self, limit: int = 100) -> dict:
        if not isinstance(limit, int) or not 1 <= limit <= 500:
            raise ValueError("limit must be an integer between 1 and 500")

        return self._request(
            "GET",
            "/internal/state",
            params={"limit": limit},
        )

    def commit(
        self,
        run: dict,
        articles: list[dict],
        scoring_model: str | None = None,
    ) -> dict:
        if len(articles) > 100:
            raise ValueError("State API accepts at most 100 articles per commit")

        payload = {
            "run": run,
            "articles": articles,
        }

        if scoring_model:
            payload["scoring_model"] = scoring_model

        result = self._request(
            "POST",
            "/internal/commit",
            payload=payload,
        )

        stored_count = result.get("stored_articles")

        if stored_count != len(articles):
            raise StateAPIError(
                "Stored article count does not match submitted article count"
            )

        return result


    @staticmethod
    def _validate_briefing_date(value: str) -> None:
        from datetime import date

        if not isinstance(value, str):
            raise ValueError("briefing_date must be a YYYY-MM-DD string")

        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(
                "briefing_date must use YYYY-MM-DD format"
            ) from exc

    def get_briefing_status(self, briefing_date: str) -> dict:
        self._validate_briefing_date(briefing_date)

        return self._request(
            "GET",
            "/internal/briefing/status",
            params={"date": briefing_date},
        )

    def claim_briefing(
        self,
        *,
        briefing_id: str,
        briefing_date: str,
        started_at: str,
        article_ids: list[str],
        content_hash: str | None = None,
    ) -> dict:
        self._validate_briefing_date(briefing_date)

        if not isinstance(briefing_id, str) or not briefing_id.strip():
            raise ValueError("briefing_id must be a non-empty string")

        if not isinstance(started_at, str) or not started_at.strip():
            raise ValueError("started_at must be a non-empty ISO datetime")

        if not isinstance(article_ids, list) or not 1 <= len(article_ids) <= 30:
            raise ValueError("article_ids must contain between 1 and 30 items")

        if any(not isinstance(item, str) or not item.strip() for item in article_ids):
            raise ValueError("article_ids must contain non-empty strings")

        if len(set(article_ids)) != len(article_ids):
            raise ValueError("article_ids must not contain duplicates")

        if content_hash is not None:
            valid_hash = (
                isinstance(content_hash, str)
                and len(content_hash) == 64
                and all(char in "0123456789abcdef" for char in content_hash.lower())
            )
            if not valid_hash:
                raise ValueError("content_hash must be a SHA-256 hex digest")

        payload = {
            "id": briefing_id,
            "briefing_date": briefing_date,
            "started_at": started_at,
            "article_ids": article_ids,
        }

        if content_hash is not None:
            payload["content_hash"] = content_hash

        return self._request(
            "POST",
            "/internal/briefing/claim",
            payload=payload,
        )

    def complete_briefing(
        self,
        *,
        briefing_id: str,
        briefing_date: str,
        sent_at: str,
        telegram_message_ids: list[int | str],
    ) -> dict:
        self._validate_briefing_date(briefing_date)

        if not isinstance(briefing_id, str) or not briefing_id.strip():
            raise ValueError("briefing_id must be a non-empty string")

        if not isinstance(sent_at, str) or not sent_at.strip():
            raise ValueError("sent_at must be a non-empty ISO datetime")

        if not isinstance(telegram_message_ids, list) or not telegram_message_ids:
            raise ValueError("telegram_message_ids must be a non-empty list")

        if any(
            isinstance(item, bool) or not isinstance(item, (int, str))
            or (isinstance(item, str) and not item.strip())
            for item in telegram_message_ids
        ):
            raise ValueError("telegram_message_ids must contain valid IDs")

        return self._request(
            "POST",
            "/internal/briefing/complete",
            payload={
                "id": briefing_id,
                "briefing_date": briefing_date,
                "sent_at": sent_at,
                "telegram_message_ids": telegram_message_ids,
            },
        )

    def fail_briefing(
        self,
        *,
        briefing_id: str,
        briefing_date: str,
        error_message: str,
    ) -> dict:
        self._validate_briefing_date(briefing_date)

        if not isinstance(briefing_id, str) or not briefing_id.strip():
            raise ValueError("briefing_id must be a non-empty string")

        if not isinstance(error_message, str) or not error_message.strip():
            raise ValueError("error_message must be a non-empty string")

        return self._request(
            "POST",
            "/internal/briefing/fail",
            payload={
                "id": briefing_id,
                "briefing_date": briefing_date,
                "error_message": error_message[:2000],
            },
        )

