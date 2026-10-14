"""Component 7 — Provenance Tracker.

Records, for every claim, the chain
    source document → chunk (exact locator) → extracted facts → resolved entities
    → retrieval (rank, score) → claim
so every value in an answer traces back to its file, row (or message / paragraph) and
field, and every name to the entity it was resolved to and why. The fact and entity
steps (task D6) need the provenance store; without one the trail is the v0.1 chain.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .models import Answer, Document

if TYPE_CHECKING:
    from .store import InfoStore


def _conflict_of(answer: Answer, entity_id: str | None, field: str, value: str, chunk_id: str) -> str | None:
    for c in answer.conflicts:
        if c.entity_id == entity_id and c.attribute == field:
            for v in c.values:
                if v.value == value and chunk_id in (v.sources or [v.chunk_id]):
                    return c.conflict_id
    return None


def claim_trail(answer: Answer, claim_index: int, documents: dict[str, Document],
                store: InfoStore | None = None) -> list[dict]:
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
        meta = r.chunk.metadata
        step = {
            "label": label,
            "1_source": {"doc_id": r.chunk.doc_id, "format": doc.format.value if doc else None,
                         "path": doc.path if doc else None},
            "2_chunk": {"chunk_id": r.chunk.chunk_id, "locator": r.chunk.locator, "row_number": meta.get("row_number"),
                        "page": meta.get("page"), "date": meta.get("date"), "text": r.chunk.text},
        }
        if store is not None:
            step["2a_extracted_facts"] = [
                {"field": f["field"], "value": f["value"], "raw_value": f["raw_value"], "entity_id": f["entity_id"],
                 "canonical_name": f["canonical_name"], "written_as": f["entity_mention"], "extractor": f["extractor"],
                 "confidence": f["confidence"], "fact_id": f["fact_id"],
                 "conflict_id": _conflict_of(answer, f["entity_id"], f["field"], f["value"], r.chunk.chunk_id)}
                for f in store.sql.facts_in_chunk(r.chunk.chunk_id)]
            step["2b_resolved_entities"] = [
                {"entity_id": e["entity_id"], "canonical_name": e["canonical_name"], "entity_type": e["entity_type"],
                 "written_as": e["mention"], "match_evidence": e["match_evidence"]}
                for e in store.sql.entities_in_chunk(r.chunk.chunk_id)]
        step["3_retrieval"] = {"rank": r.rank, "score": r.score, "channels": r.channels}
        step["4_claim"] = claim.text
        trail.append(step)
    return trail


def answer_trail(answer: Answer, documents: dict[str, Document], store: InfoStore | None = None) -> list[dict]:
    return [{"claim": c.text, "evidence": claim_trail(answer, i, documents, store)} for i, c in enumerate(answer.claims)]
