"""Component 2 — Information Extractor.  [STUB — implemented in Hack 1]

Turns chunks into (entity, attribute, value) ``Fact`` objects, each tagged with
its ``chunk_id``.

Planned approach:
  * Structured chunks (CSV / Excel rows): map columns to attributes directly
    via a per-sheet schema — no ML needed, confidence 1.0.
        members.csv: name → entity, medical_clearance_date → attribute, ...
  * Unstructured chunks (WhatsApp, PDF, email): LLM JSON extraction with a
    fixed attribute vocabulary; spaCy NER (en_core_web_sm) to find PERSON /
    DATE mentions as a cross-check. NER alone finds "Ravi" and "June 22" but
    not that one is the other's clearance date — hence the LLM step.
  * Normalise values (dates → ISO, phone → digits, times → HH:MM) so the
    conflict detector can compare them.
"""

from __future__ import annotations

from .models import Chunk, Fact


class InformationExtractor:
    def extract(self, chunks: list[Chunk]) -> list[Fact]:
        raise NotImplementedError("Hack 1: schema mapping for tables + LLM extraction for text")
