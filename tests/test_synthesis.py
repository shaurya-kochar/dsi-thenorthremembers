import json

from infobridge.evaluation import entity_resolution_f1, score_query
from infobridge.models import Chunk, Entity, Mention, RetrievedChunk
from infobridge.synthesis import LLMSynthesizer


def _retrieved():
    texts = ["members.csv row 5: name=Ravi Sharma; medical_clearance_date=2026-03-15",
             "[23/06/2026] Dr. Rao: Ravi S. cleared, clearance dated 22 June 2026"]
    ids = ["members.csv#row=5", "whatsapp.txt#msg=3"]
    return [RetrievedChunk(chunk=Chunk(chunk_id=i, doc_id=i.split("#")[0], locator=i.split("#")[1], text=t),
                           score=0.6, rank=n) for n, (i, t) in enumerate(zip(ids, texts), start=1)]


class FakeLLM:
    name = "fake"

    def __init__(self, payload):
        self.payload = payload

    def generate_json(self, system, prompt):
        return "```json\n" + json.dumps(self.payload) + "\n```"


def test_hallucinated_citation_is_flagged():
    llm = FakeLLM({"verdict": "yes", "summary": "Cleared [S1].",
                   "claims": [{"text": "Clearance March 15", "citations": ["S1"]},
                              {"text": "Paid in full", "citations": ["S9"]}]})
    answer = LLMSynthesizer(llm).synthesize("q", _retrieved())
    assert answer.verdict == "YES"
    assert [c.unsupported for c in answer.claims] == [False, True]
    assert [c.chunk_id for c in answer.citations] == ["members.csv#row=5"]


def test_score_query_detects_conflict_mentioned_in_text():
    llm = FakeLLM({"verdict": "YES", "summary": "Sources disagree: March 15 [S1] vs 22 June [S2].", "claims": []})
    answer = LLMSynthesizer(llm).synthesize("q", _retrieved())
    gold = {"case_id": "t", "facts": [], "conflicts": [{"id": "C1", "values": [
        {"value": "2026-03-15", "surface_any": ["march 15"], "sources": []},
        {"value": "2026-06-22", "surface_any": ["22 june"], "sources": []}]}]}
    query = {"query_id": "q", "fact_ids": [], "conflict_ids": ["C1"], "expected_verdict": "YES"}
    row = score_query(answer, query, gold)
    assert row["conflict_recall_text"] == 1.0
    assert row["conflict_recall"] == 0.0  # nothing structured in v0.1
    assert row["verdict_accuracy"] == 1.0


def test_entity_resolution_f1():
    gold = {"entities": [
        {"mentions": [{"text": "Ravi Sharma", "chunk_id": "a"}, {"text": "R. Sharma", "chunk_id": "b"}]},
        {"mentions": [{"text": "Ravi Shankar", "chunk_id": "c"}]}]}
    merged_wrongly = [Entity(entity_id="1", canonical_name="Ravi", entity_type="person", mentions=[
        Mention(text="Ravi Sharma", chunk_id="a"), Mention(text="R. Sharma", chunk_id="b"),
        Mention(text="Ravi Shankar", chunk_id="c")])]
    assert entity_resolution_f1(merged_wrongly, gold) == {"precision": 0.333, "recall": 1.0, "f1": 0.5}
