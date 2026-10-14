"""Issue #5: hybrid retrieval (dense + keyword + entity)."""

import json
from pathlib import Path

from infobridge.extraction import InformationExtractor
from infobridge.hybrid import HybridRetriever
from infobridge.ingestion import load_directory
from infobridge.resolution import EntityResolver
from infobridge.store import InfoStore

DATA = Path(__file__).resolve().parents[1] / "data" / "synthetic"


def _retriever(case: str) -> HybridRetriever:
    docs, chunks = load_directory(DATA / case / "sources")
    facts = InformationExtractor().extract(chunks)
    entities = EntityResolver().resolve(facts)
    store = InfoStore()
    store.build(docs, chunks, entities, facts)
    return HybridRetriever(store, entities)


def _recall(case: str) -> float:
    gold = json.loads((DATA / case / "gold.json").read_text())
    query = gold["queries"][0]
    ids = {r.chunk.chunk_id for r in _retriever(case).search(query["question"])}
    facts = [f for f in gold["facts"] if f["id"] in query["fact_ids"]]
    return sum(bool(set(f["sources"]) & ids) for f in facts) / len(facts)


def test_case3_retrieval_recall_at_least_090():
    assert _recall("case_03_conflict") >= 0.9  # dense-only baseline: 0.57


def test_other_cases_recall():
    assert _recall("case_01_simple") == 1.0
    assert _recall("case_02_medium") >= 0.9


def test_finds_entities_named_in_question():
    r = _retriever("case_03_conflict")
    asked = r.entities_in("Is Ravi Sharma eligible for the Half Marathon Training Programme Batch 2026B?")
    assert asked == ["person:ravi-sharma", "programme:hmtp-2026b"]
    assert r.entities_in("Is Ravi Shankar a member?") == ["person:ravi-shankar"]
    assert _retriever("case_04_sunday_long_run").entities_in(
        "How many volunteers confirmed for the Sunday long run, and who is the lead?") == ["event:sunday-long-run"]


def test_lookalike_chunks_are_dropped_and_channels_recorded():
    results = _retriever("case_03_conflict").search(
        "Is Ravi Sharma eligible for the Half Marathon Training Programme Batch 2026B?")
    ids = {r.chunk.chunk_id for r in results}
    assert "members.csv#row=5" in ids and "registrations.csv#row=3" in ids  # rows dense retrieval missed
    assert not {"members.csv#row=4", "registrations.csv#row=5", "whatsapp_coach_group.txt#msg=10"} & ids  # Ravi Shankar
    assert all(r.channels for r in results)
    assert [r.rank for r in results] == list(range(1, len(results) + 1))
