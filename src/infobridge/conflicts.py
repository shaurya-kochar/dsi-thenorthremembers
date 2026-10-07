"""Component 5b — Conflict Detector.  [STUB — implemented in Hack 1]

Deterministic, not LLM-based, so precision/recall are measurable:
  1. Group facts by (resolved entity_id, attribute).
  2. If the group holds >1 distinct *normalised* value → Conflict.
  3. Severity: high if the disagreement changes a decision rule outcome,
     medium for dates/counts, low for formatting-only differences.
  4. Suggestion heuristics: prefer most recent source, prefer official
     document over chat, prefer source closest to the fact's owner.

Scored against ``gold.json["conflicts"]`` (planted contradictions).
"""

from __future__ import annotations

from .models import Conflict, Entity, Fact


class ConflictDetector:
    def detect(self, entities: list[Entity], facts: list[Fact]) -> list[Conflict]:
        raise NotImplementedError("Hack 1: group by (entity, attribute), compare normalised values")
