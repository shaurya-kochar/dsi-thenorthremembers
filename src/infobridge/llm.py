"""Thin LLM wrapper. Kept to one small class instead of LangChain so prompt and
citation behaviour stay easy to inspect while the pipeline is being built.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from .config import settings

CACHE_DIR = Path(__file__).resolve().parents[2] / "results" / "cache"
TIMEOUT_MS = 300_000  # calls normally take 20-130 s


class GeminiLLM:
    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        from google import genai  # imported lazily so the extractive backend needs no key
        from google.genai import types

        key = api_key or settings.gemini_api_key
        if not key:
            raise RuntimeError("GEMINI_API_KEY is not set. Add it to .env or use --backend extractive.")
        # without a timeout a stalled request hangs the run for good; with one it is retried
        self.client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=TIMEOUT_MS))
        self.model = model or settings.model
        self.name = f"gemini:{self.model}"

    def generate_json(self, system: str, prompt: str, retries: int = 3) -> str:
        """JSON-mode completion. Identical calls are served from a disk cache
        (``results/cache/``) so re-runs don't spend free-tier quota."""
        key = hashlib.sha256(json.dumps([self.model, system, prompt]).encode()).hexdigest()[:24]
        cached = CACHE_DIR / f"{key}.json"
        if settings.llm_cache and cached.exists():
            return json.loads(cached.read_text())["text"]
        text = self._call(system, prompt, retries)
        if settings.llm_cache:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cached.write_text(json.dumps({"model": self.model, "text": text}))
        return text

    def _call(self, system: str, prompt: str, retries: int) -> str:
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
            except Exception as e:  # rate limits / transient errors on the free tier
                if attempt == retries - 1 or "PerDay" in str(e):
                    raise  # a spent daily quota does not come back within the retries
                time.sleep(min(60, 2 * 2**attempt))  # 2, 4, 8, ... up to 60 s (overload / rate limits)
        return ""
