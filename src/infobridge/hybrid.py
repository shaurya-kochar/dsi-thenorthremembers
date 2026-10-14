"""Component 5 — Retrieval (issue #5): dense + keyword + entity-based search.

Dense retrieval alone misses spreadsheet rows (they embed poorly next to chat messages)
and ranks look-alikes above the person asked about. So a question goes through three
channels and the results are merged:
  1. dense    top-k chunks from the vector store (all-MiniLM-L6-v2)
  2. keyword  BM25 over the chunk text, for names and ids
  3. entity   the people / events / programmes / places named in the question are found
              with the name finder and the resolver's name rules, and every chunk about
              them is fetched from the knowledge graph, plus the chunks of programmes and
              events linked to them (e.g. the programme a person registered for).
Chunks that only mention a look-alike of the person asked about (same first name, not
the same entity) are dropped. Each result says which channels found it.
"""

from __future__ import annotations

import math
import re
from collections import Counter

from .extraction import NameFinder
from .models import Chunk, Entity, RetrievedChunk
from .resolution import is_full, name_tokens, names_compatible, other_names_compatible, _Embedder, _strip_qualifiers
from .store import InfoStore

WORD = re.compile(r"[a-z0-9]+")
STOP = set("the a an of for to in on at is are was were and or who what when where how many much did do does "
           "has have had be been by with from this that which it as".split())


class BM25:
    def __init__(self, chunks: list[Chunk], k1: float = 1.5, b: float = 0.75):
        self.chunks = chunks
        self.docs = [[w for w in WORD.findall(c.text.lower()) if w not in STOP] for c in chunks]
        self.avg = sum(map(len, self.docs)) / max(len(self.docs), 1)
        df = Counter(w for d in self.docs for w in set(d))
        n = len(self.docs)
        self.idf = {w: math.log(1 + (n - f + 0.5) / (f + 0.5)) for w, f in df.items()}
        self.tf = [Counter(d) for d in self.docs]
        self.k1, self.b = k1, b

    def search(self, query: str, k: int) -> list[tuple[Chunk, float]]:
        terms = [w for w in WORD.findall(query.lower()) if w not in STOP]
        scores = []
        for chunk, tf, doc in zip(self.chunks, self.tf, self.docs):
            s = sum(self.idf.get(t, 0) * tf[t] * (self.k1 + 1) /
                    (tf[t] + self.k1 * (1 - self.b + self.b * len(doc) / self.avg)) for t in terms if t in tf)
            if s > 0:
                scores.append((chunk, s))
        return sorted(scores, key=lambda x: -x[1])[:k]


class HybridRetriever:
    def __init__(self, store: InfoStore, entities: list[Entity], k_dense: int = 8, k_keyword: int = 5,
                 max_results: int = 16):
        self.store = store
        self.entities = {e.entity_id: e for e in entities}
        self.finder = NameFinder(list(store.chunks.values()))
        self.bm25 = BM25(list(store.chunks.values()))
        self.k_dense, self.k_keyword, self.max_results = k_dense, k_keyword, max_results
        self.embedder = _Embedder()

    # -------------------------------------------------------- question -> entities

    def entities_in(self, question: str) -> list[str]:
        found = set()
        surfaces = self.finder.find(question)
        for e in self.entities.values():  # event / place names written in any case ("Sunday long run")
            if e.entity_type in ("event", "location"):
                for m in e.mentions:
                    name = _strip_qualifiers(m.text)
                    if len(name) > 3 and re.search(rf"\b{re.escape(name)}\b", question, re.IGNORECASE):
                        surfaces.append((m.text, e.entity_type))
        for surface, etype in surfaces:
            for e in self.entities.values():
                if e.entity_type != etype:
                    continue
                if etype == "person":
                    asked = name_tokens(surface)
                    hit = any(names_compatible(asked, name_tokens(m.text)) and
                              (not is_full(asked) or is_full(name_tokens(m.text))) for m in e.mentions)
                    # a full name in the question must match a full name of the entity
                    if hit and is_full(asked):
                        hit = any(is_full(name_tokens(m.text)) and names_compatible(asked, name_tokens(m.text))
                                  for m in e.mentions)
                else:
                    hit = any(other_names_compatible(surface, m.text, etype, self.embedder) for m in e.mentions)
                if hit:
                    found.add(e.entity_id)
        return sorted(found)

    def lookalikes(self, asked: list[str]) -> set[str]:
        """People who share a first name with a person asked about but are someone else."""
        firsts = {name_tokens(m.text)[0] for a in asked if self.entities[a].entity_type == "person"
                  for m in self.entities[a].mentions if name_tokens(m.text)}
        return {e.entity_id for e in self.entities.values() if e.entity_type == "person" and e.entity_id not in asked
                and any(name_tokens(m.text) and name_tokens(m.text)[0] in firsts for m in e.mentions)}

    # -------------------------------------------------------------------- search

    def search(self, question: str, k: int | None = None) -> list[RetrievedChunk]:
        graph = self.store.graph
        found: dict[str, dict] = {}

        def add(chunk_id: str, channel: str, score: float) -> None:
            entry = found.setdefault(chunk_id, {"channels": [], "score": 0.0})
            entry["channels"].append(channel)
            entry["score"] = max(entry["score"], score)

        for r in self.store.vectors.search(question, k or self.k_dense):
            add(r.chunk.chunk_id, "dense", r.score)
        for chunk, _ in self.bm25.search(question, self.k_keyword):
            add(chunk.chunk_id, "keyword", 0.0)

        asked = self.entities_in(question)
        if graph is not None:
            for entity_id in asked:
                for chunk_id in graph.chunks_for_entity(entity_id):
                    add(chunk_id, f"entity:{entity_id}", 0.0)
                asked_type = self.entities[entity_id].entity_type
                # a person -> the programmes / events they are linked to; an event or place -> its people
                wanted = ("programme", "event") if asked_type == "person" else ("person",)
                for linked in graph.related_entities(entity_id):
                    if self.entities.get(linked) and self.entities[linked].entity_type in wanted:
                        for chunk_id in graph.chunks_for_entity(linked):
                            add(chunk_id, f"linked:{linked}", 0.0)

            lookalikes = self.lookalikes(asked)
            asked_people = {a for a in asked if self.entities[a].entity_type == "person"}
            for chunk_id in list(found):
                here = {graph.entity_of(m.text, chunk_id) for e in self.entities.values()
                        for m in e.mentions if m.chunk_id == chunk_id}
                if here & lookalikes and not here & asked_people:
                    del found[chunk_id]  # only about someone with the same first name

        dense_scores = {r.chunk.chunk_id: r.score for r in self.store.vectors.search(question, len(self.store.chunks))}

        def priority(item):
            chunk_id, entry = item
            direct = any(c.startswith("entity:") for c in entry["channels"])
            return (not direct, -dense_scores.get(chunk_id, 0.0))

        ranked = sorted(found.items(), key=priority)[: max(self.max_results, k or 0)]
        return [RetrievedChunk(chunk=self.store.chunks[cid], score=round(max(e["score"], dense_scores.get(cid, 0.0)), 4),
                               rank=i, channels=e["channels"])
                for i, (cid, e) in enumerate(ranked, start=1)]
