import os

from dotenv import load_dotenv
from google import genai


load_dotenv()


class GeminiClient:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        self.model = os.getenv(
            "GEMINI_MODEL",
            "gemini-3.8-flash"
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
