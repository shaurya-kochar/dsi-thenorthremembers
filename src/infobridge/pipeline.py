"""End-to-end pipeline: ingest sources → index → answer questions with citations.

Full path (Hack 1, task D4):
    ingest → extract facts (tables, names; text with the LLM) → resolve entities →
    detect conflicts → build store (vectors + knowledge graph + provenance tables) →
    hybrid retrieve → conflict-aware synthesis with confidence
Baseline path (v0.1, kept for the before/after comparison):
    ingest → vector store → dense top-k → naive RAG synthesis, no conflicts
Both modes share one ingestion, so ``ask(question, mode=...)`` can switch per question.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

from .config import settings
from .conflicts import ConflictDetector
from .extraction import InformationExtractor
from .hybrid import HybridRetriever
from .ingestion import load_directory
from .models import Answer, Chunk, Conflict, Document, Entity, Fact, RetrievedChunk
from .resolution import EntityResolver
from .store import InfoStore
from .synthesis import ExtractiveSynthesizer, LLMSynthesizer, cite_conflicts, fallback_answer

MODES = ("baseline", "full")
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def make_synthesizer(backend: str | None = None):
    backend = backend or settings.backend
    if backend == "extractive":
        return ExtractiveSynthesizer()
    if backend == "gemini":
        from .llm import GeminiLLM

        return LLMSynthesizer(GeminiLLM())
    raise ValueError(f"Unknown backend: {backend}")


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", text.lower()) if len(w) > 3}


def _asks_about(conflict: Conflict, question: str) -> bool:
    """'volunteer_count' is asked about in 'How many volunteers confirmed ...'."""
    asked = _words(question)
    return any(a.startswith(w) or w.startswith(a) for w in _words(conflict.attribute.replace("_", " ")) for a in asked)


class InfoBridge:
    def __init__(self, backend: str | None = None, top_k: int | None = None, min_score: float | None = None,
                 mode: str = "full", llm_extraction: bool | None = None):
        if mode not in MODES:
            raise ValueError(f"Unknown mode: {mode} (expected one of {MODES})")
        self.backend = backend or settings.backend
        self.synthesizer = make_synthesizer(self.backend)
        self.top_k = top_k or settings.top_k
        self.min_score = settings.min_score if min_score is None else min_score
        self.mode = mode
        # text facts need Gemini; by default they are extracted whenever the Gemini backend is used
        self.llm_extraction = (self.backend == "gemini" and bool(settings.gemini_api_key)
                               if llm_extraction is None else llm_extraction)
        self.store = InfoStore()
        self.documents: dict[str, Document] = {}
        self.chunks: dict[str, Chunk] = {}
        self.facts: list[Fact] = []
        self.entities: list[Entity] = []
        self.conflicts: list[Conflict] = []
        self.extraction_failed: list[str] = []  # documents whose LLM extraction failed (their text facts are missing)
        self.retriever: HybridRetriever | None = None

    def ingest(self, source_dir: str | Path) -> None:
        docs, chunks = load_directory(source_dir)
        self.documents.update({d.doc_id: d for d in docs})
        self.chunks.update({c.chunk_id: c for c in chunks})
        chunks = list(self.chunks.values())  # everything ingested so far is resolved and indexed together

        text_extractor = None
        if self.llm_extraction:
            from .llm import GeminiLLM
            from .llm_extraction import LLMFactExtractor

            text_extractor = LLMFactExtractor(GeminiLLM())
        self.facts = InformationExtractor(text_extractor).extract(chunks)
        self.extraction_failed = list(text_extractor.failed) if text_extractor else []
        self.entities = EntityResolver().resolve(self.facts)
        self.conflicts = ConflictDetector().detect(self.entities, self.facts, self.chunks)  # before the graph: edges get conflict ids
        self.store = InfoStore()
        self.store.build(list(self.documents.values()), chunks, self.entities, self.facts, self.conflicts)
        self.retriever = HybridRetriever(self.store, self.entities, k_dense=self.top_k)

    def ask(self, question: str, mode: str | None = None) -> Answer:
        mode = mode or self.mode
        if mode not in MODES:
            raise ValueError(f"Unknown mode: {mode} (expected one of {MODES})")
        start = time.perf_counter()
        if mode == "baseline":
            asked: list[str] = []
            retrieved = self.store.vectors.search(question, self.top_k)
            if not retrieved or retrieved[0].score < self.min_score:
                answer = fallback_answer(question, retrieved, self.synthesizer.name)
            else:
                answer = self.synthesizer.synthesize(question, retrieved)
        else:
            retrieved = self.retriever.search(question) if self.retriever else []
            asked = self.retriever.entities_in(question) if self.retriever else []
            best = max((r.score for r in retrieved), default=0.0)
            if not retrieved or (best < self.min_score and not asked):
                answer = fallback_answer(question, retrieved, self.synthesizer.name)
            else:
                conflicts = self.relevant_conflicts(question, asked, retrieved)
                retrieved, conflicts = cite_conflicts(retrieved, conflicts, self.store.chunks)
                by_id = {e.entity_id: e for e in self.entities}
                answer = self.synthesizer.synthesize(question, retrieved, conflicts, [by_id[a] for a in asked])
        answer.entities = asked
        answer.mode = mode
        answer.latency_s = round(time.perf_counter() - start, 3)
        return answer

    def relevant_conflicts(self, question: str, asked: list[str], retrieved: list[RetrievedChunk]) -> list[Conflict]:
        """Conflicts on the entities asked about, and on entities linked to them (the programme a person
        registered for, the volunteers of an event) when the evidence about them was retrieved. Look-alikes
        of a person asked about are never included. Ordered by relevance to the question, then severity."""
        graph = self.store.graph
        related = {e for a in asked for e in graph.related_entities(a)} - self.retriever.lookalikes(asked) - set(asked)
        retrieved_ids = {r.chunk.chunk_id for r in retrieved}
        relevant = [c for c in self.conflicts
                    if c.entity_id in asked or (c.entity_id in related and any(
                        s in retrieved_ids for v in c.values for s in (v.sources or [v.chunk_id])))]
        return sorted(relevant, key=lambda c: (c.entity_id not in asked, not _asks_about(c, question),
                                               SEVERITY_ORDER.get(c.severity, 3), c.conflict_id))
