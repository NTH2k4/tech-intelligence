import json
import logging
import os
from collections.abc import Callable
from typing import Any

import httpx
from dotenv import load_dotenv
from google import genai
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_random_exponential,
)


load_dotenv()

logger = logging.getLogger(__name__)

# Retry only failures that are normally transient. Authentication, permission,
# invalid-request, and other 4xx errors fail immediately.
_RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}
_RETRYABLE_EXCEPTION_NAMES = {
    "deadlineexceeded",
    "internalservererror",
    "resourceexhausted",
    "serviceunavailable",
}


def _status_code(exc: BaseException) -> int | None:
    """Extract an HTTP status from Google API errors without logging payloads."""
    candidates = (
        getattr(exc, "code", None),
        getattr(exc, "status_code", None),
        getattr(getattr(exc, "response", None), "status_code", None),
    )
    for candidate in candidates:
        try:
            if candidate is not None:
                return int(candidate)
        except (TypeError, ValueError):
            continue
    return None


def _is_retryable_gemini_error(exc: BaseException) -> bool:
    """Return True only for transient API or transport failures."""
    if isinstance(exc, httpx.TransportError):
        return True

    status = _status_code(exc)
    if status in _RETRYABLE_STATUS_CODES:
        return True

    # Some SDK exception variants expose a useful class name but no status.
    return exc.__class__.__name__.replace("_", "").lower() in _RETRYABLE_EXCEPTION_NAMES


@retry(
    retry=retry_if_exception(_is_retryable_gemini_error),
    wait=wait_random_exponential(multiplier=1, max=20),
    stop=stop_after_attempt(4),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def _retry_gemini_call(
    call: Callable[..., Any],
    request_kwargs: dict[str, Any],
) -> Any:
    """Retry the API transport call, not response parsing or validation."""
    return call(**request_kwargs)


class GeminiClient:
    def __init__(self, model: str | None = None):
        api_key = os.getenv("GEMINI_API_KEY")
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured")

        self.client = genai.Client(api_key=api_key)

    def _create_interaction(self, **request_kwargs: Any) -> Any:
        try:
            return _retry_gemini_call(
                self.client.interactions.create,
                request_kwargs,
            )
        except Exception as exc:
            status = _status_code(exc)
            status_detail = f", HTTP {status}" if status is not None else ""
            raise RuntimeError(
                "Gemini API request failed after transient-error retries: "
                f"{type(exc).__name__}{status_detail}"
            ) from exc

    def generate(self, prompt: str) -> str:
        if not prompt or not prompt.strip():
            raise ValueError("Prompt cannot be empty")

        interaction = self._create_interaction(
            model=self.model,
            input=prompt,
            store=False,
        )
        result = (interaction.output_text or "").strip()

        if not result:
            raise RuntimeError("Gemini returned an empty response")

        return result

    def generate_json(self, prompt: str, schema: dict) -> dict:
        if not prompt or not prompt.strip():
            raise ValueError("Prompt cannot be empty")

        interaction = self._create_interaction(
            model=self.model,
            input=prompt,
            store=False,
            response_format={
                "type": "text",
                "mime_type": "application/json",
                "schema": schema,
            },
        )
        output = (interaction.output_text or "").strip()

        if not output:
            raise RuntimeError("Gemini returned empty JSON")

        try:
            result = json.loads(output)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Gemini returned invalid JSON") from exc

        if not isinstance(result, dict):
            raise RuntimeError("Gemini output must be a JSON object")

        return result
