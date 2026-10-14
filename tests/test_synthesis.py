import json

from infobridge.evaluation import entity_resolution_f1, score_query
from infobridge.models import Answer, Chunk, Claim, Conflict, ConflictValue, Entity, Mention, RetrievedChunk
from infobridge.synthesis import LLMSynthesizer, assess_confidence, cite_conflicts


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


def test_llm_responses_are_cached(tmp_path, monkeypatch):
    import infobridge.llm as llm_mod

    monkeypatch.setattr(llm_mod, "CACHE_DIR", tmp_path)
    from dataclasses import replace

    monkeypatch.setattr(llm_mod, "settings", replace(llm_mod.settings, llm_cache=True))
    llm = object.__new__(llm_mod.GeminiLLM)  # skip __init__: no API key needed
    llm.model, llm.name = "test-model", "gemini:test-model"
    calls = []
    monkeypatch.setattr(llm, "_call", lambda system, prompt, retries: calls.append(prompt) or '{"ok": 1}')

    assert llm.generate_json("sys", "p1") == '{"ok": 1}'
    assert llm.generate_json("sys", "p1") == '{"ok": 1}'  # served from disk
    llm.generate_json("sys", "p2")
    assert calls == ["p1", "p2"]


def _chunk(chunk_id: str) -> Chunk:
    return Chunk(chunk_id=chunk_id, doc_id=chunk_id.split("#")[0], locator=chunk_id.split("#")[1], text=chunk_id)


def test_cite_conflicts_adds_a_missing_side_with_the_next_rank():
    retrieved = [RetrievedChunk(chunk=_chunk("plan.pdf#page=1&para=5"), score=0.7, rank=1, channels=["dense"])]
    conflict = Conflict(conflict_id="C1", entity_id="event:x", attribute="volunteer_count", values=[
        ConflictValue(value="14", raw_value="14", chunk_id="plan.pdf#page=1&para=5"),
        ConflictValue(value="12", raw_value="12 confirmed", chunk_id="chat.txt#msg=5")])
    out, [cited] = cite_conflicts(retrieved, [conflict], {"chat.txt#msg=5": _chunk("chat.txt#msg=5")})
    assert [(r.chunk.chunk_id, r.rank, r.channels) for r in out] == [
        ("plan.pdf#page=1&para=5", 1, ["dense"]), ("chat.txt#msg=5", 2, ["conflict:C1"])]
    assert len(retrieved) == 1 and [v.chunk_id for v in cited.values] == ["plan.pdf#page=1&para=5", "chat.txt#msg=5"]


def test_confidence_rules():
    strong = [RetrievedChunk(chunk=_chunk("a.csv#row=2"), score=0.8, rank=1)]
    weak = [RetrievedChunk(chunk=_chunk("a.csv#row=2"), score=0.2, rank=1)]
    ok = Claim(text="x", citations=["S1"])
    conflict = Conflict(conflict_id="C1", entity_id="event:x", entity_name="Sunday Long Run",
                        attribute="volunteer_count", values=[
                            ConflictValue(value="14", raw_value="14", chunk_id="a"),
                            ConflictValue(value="12", raw_value="12 confirmed", chunk_id="b")])
    answer = lambda **kw: Answer(question="q", summary="s", **{"claims": [ok], **kw})
    assert assess_confidence(answer(fallback=True), strong)[0] == "low"
    assert assess_confidence(answer(claims=[ok, Claim(text="y", citations=[], unsupported=True)]), strong) == \
        ("low", "1 of 2 claims do not cite a retrieved source.")
    assert assess_confidence(answer(verdict="UNCERTAIN"), strong)[0] == "low"
    assert assess_confidence(answer(conflicts=[conflict]), strong) == \
        ("medium", "Two sources disagree on the volunteer count of Sunday Long Run (14 vs 12).")
    assert assess_confidence(answer(conflicts=[conflict, conflict]), strong)[1].endswith(", and 1 more conflict is open.")
    assert assess_confidence(answer(), weak)[0] == "medium"
    assert assess_confidence(answer(verdict="YES"), strong)[0] == "high"
