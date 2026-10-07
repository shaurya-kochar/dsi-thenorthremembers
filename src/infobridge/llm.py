"""Thin LLM wrapper. Kept to one small class instead of LangChain so prompt and
citation behaviour stay easy to inspect while the pipeline is being built.
"""

from __future__ import annotations

import time

from .config import settings


class GeminiLLM:
    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        from google import genai  # imported lazily so the extractive backend needs no key

        key = api_key or settings.gemini_api_key
        if not key:
            raise RuntimeError("GEMINI_API_KEY is not set. Add it to .env or use --backend extractive.")
        self.client = genai.Client(api_key=key)
        self.model = model or settings.model
        self.name = f"gemini:{self.model}"

    def generate_json(self, system: str, prompt: str, retries: int = 3) -> str:
        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=0.0,
            response_mime_type="application/json",
        )
        for attempt in range(retries):
            try:
                resp = self.client.models.generate_content(model=self.model, contents=prompt, config=config)
                return resp.text or ""
            except Exception:  # rate limits / transient errors on the free tier
                if attempt == retries - 1:
                    raise
                time.sleep(2 * 2**attempt)
        return ""
