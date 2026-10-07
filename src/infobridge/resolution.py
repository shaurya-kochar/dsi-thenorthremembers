"""Component 3 — Entity Resolver.  [STUB — implemented in Hack 1]

Clusters mentions that refer to the same real-world entity:
    "Ravi Sharma" (members.csv) = "R. Sharma" (registrations.csv) = "Ravi S." (WhatsApp)
while keeping look-alikes apart:
    "Ravi Shankar" ≠ "Ravi Sharma",   "Srinivas Reddy" ≠ "Srinivas Rao Kumar"

Planned approach (in priority order):
  1. Strong keys: identical normalised phone / email / member id → same entity.
  2. Name compatibility: initials expansion ("R. Sharma" ~ "Ravi Sharma"),
     prefix nicknames ("Srini" ~ "Srinivas"), rapidfuzz token_sort_ratio,
     phonetic encoding (Double Metaphone) for spelling variants.
  3. Context: same chat thread / co-occurring attributes break ties.
  4. Every merge records ``match_evidence`` for the provenance trail.

Scored with pairwise F1 against ``gold.json["entities"]``
(see ``evaluation.entity_resolution_f1``).
"""

from __future__ import annotations

from .models import Entity, Fact


class EntityResolver:
    def resolve(self, facts: list[Fact]) -> list[Entity]:
        raise NotImplementedError("Hack 1: strong keys → fuzzy names → context")
