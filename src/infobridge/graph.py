"""Component 4 — Knowledge Graph Builder.  [STUB — implemented in Hack 1]

NetworkX MultiDiGraph:
  nodes  entity_id (person / event / programme / location) and attribute values
  edges  entity --attribute--> value, with edge data
         {"chunk_id": ..., "doc_id": ..., "fact_id": ..., "extractor": ...}
         so every edge is a provenance edge.
Conflict markers: when one (entity, attribute) has >1 distinct value edge,
the edges get ``conflict_id`` set by the conflict detector.

Used by synthesis for graph-traversal retrieval (hybrid search) and by the
UI's knowledge-graph screen.
"""

from __future__ import annotations

from .models import Conflict, Entity, Fact


class KnowledgeGraphBuilder:
    def build(self, entities: list[Entity], facts: list[Fact], conflicts: list[Conflict]):
        raise NotImplementedError("Hack 1: networkx MultiDiGraph with provenance edges")
