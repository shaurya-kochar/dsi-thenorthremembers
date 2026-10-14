"""Component 4 — Knowledge graph (issue #4).

A NetworkX ``MultiDiGraph``:
  entity nodes     ``entity_id`` with canonical name and type
  value nodes      ``value:<attribute>=<value>``
  chunk nodes      ``chunk:<chunk_id>``
  edges            entity --attribute--> value (one edge per fact), storing chunk_id, doc_id, fact_id, raw value and
                   (once the conflict detector runs) conflict_id; entity --mentioned_in--> chunk.
So every edge is a provenance edge. Used by retrieval to fetch every chunk about an entity.
"""

from __future__ import annotations

import networkx as nx

from .models import Conflict, Entity, Fact

MENTIONED_IN = "mentioned_in"


class KnowledgeGraph:
    def __init__(self, graph: nx.MultiDiGraph, mention_index: dict[tuple[str, str], str]):
        self.graph = graph
        self.mention_index = mention_index  # (mention text, chunk_id) -> entity_id

    def entity_of(self, mention: str, chunk_id: str) -> str | None:
        return self.mention_index.get((mention, chunk_id))

    def entities(self, entity_type: str | None = None) -> list[str]:
        return [n for n, d in self.graph.nodes(data=True)
                if d.get("kind") == "entity" and (entity_type is None or d.get("entity_type") == entity_type)]

    def chunks_for_entity(self, entity_id: str) -> set[str]:
        if entity_id not in self.graph:
            return set()
        return {d["chunk_id"] for _, _, d in self.graph.out_edges(entity_id, data=True)}

    def facts_for_entity(self, entity_id: str) -> list[dict]:
        if entity_id not in self.graph:
            return []
        return [d for _, _, k, d in self.graph.out_edges(entity_id, keys=True, data=True) if k != MENTIONED_IN]

    def related_entities(self, entity_id: str) -> set[str]:
        """Entities mentioned in the same chunks (e.g. the programme in a registration row)."""
        related = set()
        for chunk_id in self.chunks_for_entity(entity_id):
            related |= {u for u, _, k in self.graph.in_edges(f"chunk:{chunk_id}", keys=True) if k == MENTIONED_IN}
        return related - {entity_id}


class KnowledgeGraphBuilder:
    def build(self, entities: list[Entity], facts: list[Fact], conflicts: list[Conflict] | None = None) -> KnowledgeGraph:
        g = nx.MultiDiGraph()
        index = {}
        for e in entities:
            g.add_node(e.entity_id, kind="entity", name=e.canonical_name, entity_type=e.entity_type)
            for m in e.mentions:
                index[(m.text, m.chunk_id)] = e.entity_id
                g.add_node(f"chunk:{m.chunk_id}", kind="chunk")
                g.add_edge(e.entity_id, f"chunk:{m.chunk_id}", key=MENTIONED_IN, chunk_id=m.chunk_id,
                           doc_id=m.chunk_id.split("#")[0], mention=m.text)
        conflict_of = {}
        for c in conflicts or []:
            for v in c.values:
                for chunk_id in v.sources or [v.chunk_id]:
                    conflict_of[(c.entity_id, c.attribute, v.value, chunk_id)] = c.conflict_id
        for f in facts:
            entity_id = index.get((f.entity_mention, f.chunk_id))
            if entity_id is None or f.attribute == "mention":
                continue
            value_node = f"value:{f.attribute}={f.value}"
            g.add_node(value_node, kind="value", value=f.value)
            # keyed by fact: the same value stated in several rows is one edge per source, not one edge
            g.add_edge(entity_id, value_node, key=f.fact_id, attribute=f.attribute, chunk_id=f.chunk_id,
                       doc_id=f.chunk_id.split("#")[0], fact_id=f.fact_id, raw_value=f.raw_value, extractor=f.extractor,
                       conflict_id=conflict_of.get((entity_id, f.attribute, f.value, f.chunk_id)))
        return KnowledgeGraph(g, index)
