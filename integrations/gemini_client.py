import os
import json

from dotenv import load_dotenv
from google import genai


load_dotenv()


class GeminiClient:
    def __init__(self, model: str | None = None):
        api_key = os.getenv("GEMINI_API_KEY")
        self.model = model or os.getenv(
            "GEMINI_MODEL",
            "gemini-3.6-flash"
        )

        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not configured"
            )

        self.client = genai.Client(api_key=api_key)

    def generate(self, prompt: str) -> str:
        if not prompt or not prompt.strip():
            raise ValueError("Prompt cannot be empty")

        try:
            interaction = self.client.interactions.create(
                model=self.model,
                input=prompt,
                store=False
            )

            result = (interaction.output_text or "").strip()

            if not result:
                raise RuntimeError(
                    "Gemini returned an empty response"
                )

            return result

        except Exception as exc:
            raise RuntimeError(
                f"Gemini API request failed: {type(exc).__name__}"
            ) from exc


    def generate_json(
        self,
        prompt: str,
        schema: dict
    ) -> dict:
        if not prompt.strip():
            raise ValueError("Prompt cannot be empty")

        interaction = self.client.interactions.create(
            model=self.model,
            input=prompt,
            store=False,
            response_format={
                "type": "text",
                "mime_type": "application/json",
                "schema": schema
            }
        )

        output = (interaction.output_text or "").strip()

        if not output:
            raise RuntimeError("Gemini returned empty JSON")

        try:
            result = json.loads(output)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "Gemini returned invalid JSON"
            ) from exc

        if not isinstance(result, dict):
            raise RuntimeError(
                "Gemini output must be a JSON object"
            )

        return result
