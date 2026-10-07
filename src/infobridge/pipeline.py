"""End-to-end pipeline: ingest sources → index → answer questions with citations.

v0.1 path:   ingest → vector store → retrieve → synthesise → validate citations
Hack 1 path: ingest → extract facts → resolve entities → detect conflicts →
             build KG → hybrid retrieve → conflict-aware synthesis
The Hack 1 stages plug in at the marked points below.
"""

from __future__ import annotations

import time
from pathlib import Path

from .config import settings
from .ingestion import load_directory
from .models import Answer, Chunk, Document
from .retrieval import VectorStore
from .synthesis import ExtractiveSynthesizer, LLMSynthesizer, fallback_answer


def make_synthesizer(backend: str | None = None):
    backend = backend or settings.backend
    if backend == "extractive":
        return ExtractiveSynthesizer()
    if backend == "gemini":
        from .llm import GeminiLLM

        return LLMSynthesizer(GeminiLLM())
    raise ValueError(f"Unknown backend: {backend}")


class InfoBridge:
    def __init__(self, backend: str | None = None, top_k: int | None = None, min_score: float | None = None):
        self.synthesizer = make_synthesizer(backend)
        self.top_k = top_k or settings.top_k
        self.min_score = settings.min_score if min_score is None else min_score
        self.store = VectorStore()
        self.documents: dict[str, Document] = {}
        self.chunks: dict[str, Chunk] = {}

    def ingest(self, source_dir: str | Path) -> None:
        docs, chunks = load_directory(source_dir)
        self.documents.update({d.doc_id: d for d in docs})
        self.chunks.update({c.chunk_id: c for c in chunks})
        self.store.add(chunks)
        # HACK 1: facts = extractor.extract(chunks); entities = resolver.resolve(facts);
        #         conflicts = detector.detect(entities, facts); graph = kg.build(...)

    def ask(self, question: str) -> Answer:
        start = time.perf_counter()
        retrieved = self.store.search(question, self.top_k)
        # HACK 1: expand `retrieved` via the KG (all chunks mentioning entities in the top hits)
        if not retrieved or retrieved[0].score < self.min_score:
            answer = fallback_answer(question, retrieved, self.synthesizer.name)
        else:
            answer = self.synthesizer.synthesize(question, retrieved)
        # HACK 1: answer.conflicts = conflicts touching entities in the answer
        answer.latency_s = round(time.perf_counter() - start, 3)
        return answer
