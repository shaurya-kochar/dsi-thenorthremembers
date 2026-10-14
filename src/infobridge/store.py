"""Component 4 — Storage (issue #4): vector store + knowledge graph + SQLite provenance tables.

``InfoStore.build`` takes everything the earlier stages produced and makes it queryable:
  * ``vectors``   ChromaDB, for dense retrieval (``retrieval.VectorStore``)
  * ``graph``     the knowledge graph (``graph.KnowledgeGraph``)
  * ``sql``       SQLite tables: documents, chunks, entities, mentions, facts, conflicts,
                  conflict_values. Every fact row carries its entity, field, value, file,
                  row/page and date, so any value resolves to an exact place in a source.
Conflict rows have a ``status`` (open / accepted) and ``accepted_value``, which the API's
Conflict Review sets.
"""

from __future__ import annotations

import sqlite3

from .graph import KnowledgeGraph, KnowledgeGraphBuilder
from .models import Chunk, Conflict, Document, Entity, Fact
from .retrieval import VectorStore

SCHEMA = """
CREATE TABLE documents (doc_id TEXT PRIMARY KEY, path TEXT, format TEXT, title TEXT);
CREATE TABLE chunks (chunk_id TEXT PRIMARY KEY, doc_id TEXT, locator TEXT, row_number INTEGER, page INTEGER,
                     date TEXT, text TEXT);
CREATE TABLE entities (entity_id TEXT PRIMARY KEY, canonical_name TEXT, entity_type TEXT, match_evidence TEXT);
CREATE TABLE mentions (entity_id TEXT, text TEXT, chunk_id TEXT);
CREATE TABLE facts (fact_id TEXT PRIMARY KEY, entity_id TEXT, entity_mention TEXT, field TEXT, value TEXT,
                    raw_value TEXT, chunk_id TEXT, extractor TEXT, confidence REAL);
CREATE TABLE conflicts (conflict_id TEXT PRIMARY KEY, entity_id TEXT, field TEXT, severity TEXT, suggestion TEXT,
                        status TEXT DEFAULT 'open', accepted_value TEXT);
CREATE TABLE conflict_values (conflict_id TEXT, value TEXT, raw_value TEXT, chunk_id TEXT);
CREATE INDEX facts_by_entity ON facts (entity_id);
"""

FACT_QUERY = """
SELECT f.fact_id, f.entity_id, e.canonical_name, f.entity_mention, f.field, f.value, f.raw_value, f.chunk_id,
       c.doc_id AS file, c.locator, c.row_number, c.page, c.date, f.extractor, f.confidence
FROM facts f JOIN chunks c USING (chunk_id) LEFT JOIN entities e USING (entity_id)
"""


class ProvenanceStore:
    def __init__(self, path: str = ":memory:"):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def load(self, documents: list[Document], chunks: list[Chunk], entities: list[Entity], facts: list[Fact],
             conflicts: list[Conflict], graph: KnowledgeGraph) -> None:
        self.db.executemany("INSERT OR REPLACE INTO documents VALUES (?,?,?,?)",
                            [(d.doc_id, d.path, d.format.value, d.title) for d in documents])
        self.db.executemany("INSERT OR REPLACE INTO chunks VALUES (?,?,?,?,?,?,?)",
                            [(c.chunk_id, c.doc_id, c.locator, c.metadata.get("row_number"), c.metadata.get("page"),
                              c.metadata.get("date"), c.text) for c in chunks])
        self.db.executemany("INSERT OR REPLACE INTO entities VALUES (?,?,?,?)",
                            [(e.entity_id, e.canonical_name, e.entity_type, "; ".join(e.match_evidence)) for e in entities])
        self.db.executemany("INSERT INTO mentions VALUES (?,?,?)",
                            [(e.entity_id, m.text, m.chunk_id) for e in entities for m in e.mentions])
        self.db.executemany("INSERT OR REPLACE INTO facts VALUES (?,?,?,?,?,?,?,?,?)",
                            [(f.fact_id, graph.entity_of(f.entity_mention, f.chunk_id), f.entity_mention, f.attribute,
                              f.value, f.raw_value, f.chunk_id, f.extractor, f.confidence)
                             for f in facts if f.attribute != "mention"])
        self.add_conflicts(conflicts)
        self.db.commit()

    def add_conflicts(self, conflicts: list[Conflict]) -> None:
        self.db.executemany("INSERT OR REPLACE INTO conflicts (conflict_id, entity_id, field, severity, suggestion) "
                            "VALUES (?,?,?,?,?)",
                            [(c.conflict_id, c.entity_id, c.attribute, c.severity, c.suggestion) for c in conflicts])
        self.db.executemany("INSERT INTO conflict_values VALUES (?,?,?,?)",
                            [(c.conflict_id, v.value, v.raw_value, v.chunk_id) for c in conflicts for v in c.values])
        self.db.commit()

    def facts_for_entity(self, entity_id: str, field: str | None = None) -> list[dict]:
        sql, args = FACT_QUERY + " WHERE f.entity_id = ?", [entity_id]
        if field:
            sql, args = sql + " AND f.field = ?", args + [field]
        return [dict(r) for r in self.db.execute(sql + " ORDER BY f.field, c.date", args)]

    def fact(self, fact_id: str) -> dict | None:
        row = self.db.execute(FACT_QUERY + " WHERE f.fact_id = ?", [fact_id]).fetchone()
        return dict(row) if row else None

    def conflicts(self, status: str | None = None) -> list[dict]:
        sql = "SELECT * FROM conflicts" + (" WHERE status = ?" if status else "")
        rows = [dict(r) for r in self.db.execute(sql, [status] if status else [])]
        for r in rows:
            r["values"] = [dict(v) for v in self.db.execute(
                "SELECT v.value, v.raw_value, v.chunk_id, c.doc_id AS file, c.locator FROM conflict_values v "
                "JOIN chunks c USING (chunk_id) WHERE v.conflict_id = ?", [r["conflict_id"]])]
        return rows

    def accept_conflict_value(self, conflict_id: str, value: str) -> None:
        known = {r[0] for r in self.db.execute("SELECT value FROM conflict_values WHERE conflict_id = ?", [conflict_id])}
        if value not in known:
            raise ValueError(f"{value!r} is not one of the values of conflict {conflict_id}")
        self.db.execute("UPDATE conflicts SET status = 'accepted', accepted_value = ? WHERE conflict_id = ?",
                        [value, conflict_id])
        self.db.commit()


class InfoStore:
    """Everything the retrieval, synthesis and API layers read from."""

    def __init__(self, sql_path: str = ":memory:"):
        self.vectors = VectorStore()
        self.sql = ProvenanceStore(sql_path)
        self.graph: KnowledgeGraph | None = None
        self.chunks: dict[str, Chunk] = {}

    def build(self, documents: list[Document], chunks: list[Chunk], entities: list[Entity], facts: list[Fact],
              conflicts: list[Conflict] | None = None) -> None:
        conflicts = conflicts or []
        self.chunks.update({c.chunk_id: c for c in chunks})
        self.vectors.add(chunks)
        self.graph = KnowledgeGraphBuilder().build(entities, facts, conflicts)
        self.sql.load(documents, chunks, entities, facts, conflicts, self.graph)
