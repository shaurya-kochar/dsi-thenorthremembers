"""Component 7 — Provenance Tracker.

v0.1 records the chain  source document → chunk (exact locator) → retrieval
(rank, score) → claim. Hack 1 extends each trail with the extraction and
entity-resolution steps (which fact, which resolved entity, which match rule).
"""

from __future__ import annotations

from .models import Answer, Document


def claim_trail(answer: Answer, claim_index: int, documents: dict[str, Document]) -> list[dict]:
    """Evidence chain for one claim — one entry per cited source."""
    claim = answer.claims[claim_index]
    by_label = {f"S{r.rank}": r for r in answer.retrieved}
    trail = []
    for label in claim.citations:
        r = by_label.get(label)
        if r is None:
            trail.append({"label": label, "error": "cited label was never retrieved (hallucinated citation)"})
            continue
        doc = documents.get(r.chunk.doc_id)
        trail.append(
            {
                "label": label,
                "1_source": {"doc_id": r.chunk.doc_id, "format": doc.format.value if doc else None,
                             "path": doc.path if doc else None},
                "2_chunk": {"chunk_id": r.chunk.chunk_id, "locator": r.chunk.locator, "text": r.chunk.text},
                "3_retrieval": {"rank": r.rank, "score": r.score},
                "4_claim": claim.text,
            }
        )
    return trail


def answer_trail(answer: Answer, documents: dict[str, Document]) -> list[dict]:
    return [{"claim": c.text, "evidence": claim_trail(answer, i, documents)} for i, c in enumerate(answer.claims)]
