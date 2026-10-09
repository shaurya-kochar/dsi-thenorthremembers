"""Runtime settings, read from environment variables (or a ``.env`` file)."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str | None = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    # Gemini 1.5 Pro (named in the Sprint 1 doc) is retired; keep the model swappable.
    model: str = os.getenv("INFOBRIDGE_MODEL", "gemini-3.8-flash")
    # "gemini" = LLM synthesis; "extractive" = retrieval-only, no API key needed.
    backend: str = os.getenv("INFOBRIDGE_BACKEND", "gemini")
    top_k: int = int(os.getenv("INFOBRIDGE_TOP_K", "8"))
    # Below this best-chunk cosine similarity the system refuses to synthesise (fallback mode).
    min_score: float = float(os.getenv("INFOBRIDGE_MIN_SCORE", "0.25"))
    # Cache LLM responses on disk (results/cache/). Turn off to measure true latency.
    llm_cache: bool = os.getenv("INFOBRIDGE_LLM_CACHE", "1") == "1"


settings = Settings()
