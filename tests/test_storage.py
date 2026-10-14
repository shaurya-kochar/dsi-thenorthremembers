"""Issue #4: text fact extraction (with a fake LLM), knowledge graph and provenance store."""

import json
from pathlib import Path

import pytest

from infobridge.extraction import InformationExtractor
from infobridge.ingestion import load_directory
from infobridge.llm_extraction import LLMFactExtractor
from infobridge.models import Conflict, ConflictValue
from infobridge.resolution import EntityResolver
from infobridge.store import InfoStore

CASE3 = Path(__file__).resolve().parents[1] / "data" / "synthetic" / "case_03_conflict" / "sources"


class FakeLLM:
    """Answers like Gemini would for the coach group chat; one bad fact of each kind is dropped."""

    def generate_json(self, system, prompt, retries=3):
        if "whatsapp_coach_group.txt" not in prompt:
            return '{"facts": []}'
        return json.dumps({"facts": [
            {"chunk": "C3", "entity": "Ravi S.", "entity_type": "person", "attribute": "medical_clearance_date",
             "value": "22 June 2026"},
            {"chunk": "C5", "entity": "Ravi S.", "entity_type": "person", "attribute": "event_result",
             "value": "HR 10K Monsoon Run: 52:30"},
            {"chunk": "C9", "entity": "Batch B", "entity_type": "programme", "attribute": "registration_deadline",
             "value": "15 Sept"},
            {"chunk": "C3", "entity": "Ravi S.", "attribute": "shoe_size", "value": "9"},  # not an allowed attribute
            {"chunk": "C3", "entity": "Priyanka", "attribute": "phone", "value": "9999999999"},  # not in the text
            {"chunk": "C99", "entity": "Ravi S.", "attribute": "phone", "value": "1"},  # no such chunk
        ]})


@pytest.fixture(scope="module")
def built():
    docs, chunks = load_directory(CASE3)
    facts = InformationExtractor(text_extractor=LLMFactExtractor(FakeLLM())).extract(chunks)
    entities = EntityResolver().resolve(facts)
    store = InfoStore()
    conflict = Conflict(conflict_id="C1", entity_id="person:ravi-sharma", attribute="medical_clearance_date",
                        values=[ConflictValue(value="2026-03-15", raw_value="2026-03-15", chunk_id="members.csv#row=5"),
                                ConflictValue(value="2026-06-22", raw_value="22 June 2026",
                                              chunk_id="whatsapp_coach_group.txt#msg=3")])
    store.build(docs, chunks, entities, facts, [conflict])
    return facts, entities, store


def test_llm_facts_are_validated_and_normalised(built):
    facts, _, _ = built
    llm = [f for f in facts if f.extractor == "llm"]
    assert {(f.attribute, f.value) for f in llm} == {("medical_clearance_date", "2026-06-22"),
                                                     ("event_result", "HR 10K Monsoon Run: 52:30"),
                                                     ("registration_deadline", "2026-09-15")}
    assert all(f.chunk_id.startswith("whatsapp_coach_group.txt#msg=") for f in llm)


def test_store_returns_every_fact_with_file_row_and_field(built):
    _, _, store = built
    rows = store.sql.facts_for_entity("person:ravi-sharma")
    got = {(r["field"], r["value"], r["file"], r["locator"]) for r in rows}
    assert ("medical_clearance_date", "2026-03-15", "members.csv", "row=5") in got
    assert ("medical_clearance_date", "2026-06-22", "whatsapp_coach_group.txt", "msg=3") in got
    assert ("registered_on", "2026-09-10", "registrations.csv", "row=3") in got  # 'R. Sharma' resolved
    assert all(r["canonical_name"] == "Ravi Sharma" for r in rows)


def test_graph_has_provenance_edges(built):
    _, _, store = built
    chunks = store.graph.chunks_for_entity("person:ravi-sharma")
    assert {"members.csv#row=5", "registrations.csv#row=3", "whatsapp_coach_group.txt#msg=3"} <= chunks
    assert "members.csv#row=4" not in chunks  # Ravi Shankar's row
    edges = store.graph.facts_for_entity("person:ravi-sharma")
    clearance = [e for e in edges if e["attribute"] == "medical_clearance_date"]
    assert {e["conflict_id"] for e in clearance} == {"C1"} and all(e["fact_id"] for e in clearance)
    assert "programme:hmtp-2026b" in store.graph.related_entities("person:ravi-sharma")


def test_conflict_status_can_be_accepted(built):
    _, _, store = built
    assert store.sql.conflicts(status="open")[0]["values"][0]["file"] == "members.csv"
    with pytest.raises(ValueError):
        store.sql.accept_conflict_value("C1", "1999-01-01")
    store.sql.accept_conflict_value("C1", "2026-06-22")
    row = store.sql.conflicts()[0]
    assert (row["status"], row["accepted_value"]) == ("accepted", "2026-06-22")


class BrokenLLM:
    def generate_json(self, system, prompt, retries=3):
        raise RuntimeError("503 UNAVAILABLE")


def test_llm_failure_does_not_break_extraction():
    _, chunks = load_directory(CASE3)
    llm = LLMFactExtractor(BrokenLLM())
    facts = InformationExtractor(text_extractor=llm).extract(chunks)
    assert any(f.extractor == "csv_schema" for f in facts) and not any(f.extractor == "llm" for f in facts)
    assert llm.failed  # reported, not fatal
