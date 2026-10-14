"""Issue #7: pipeline wiring, conflict-aware answers and confidence.

Offline: text facts come from the fake extraction LLM of test_conflicts, answers from a fake
answering LLM that records its prompt.
"""

import json
import re
from pathlib import Path

import pytest

import infobridge.llm as llm_module
from infobridge.pipeline import InfoBridge
from infobridge.synthesis import LLMSynthesizer
from test_conflicts import FakeLLM as FakeExtractionLLM

DATA = Path(__file__).resolve().parents[1] / "data" / "synthetic"
RAVI = "Is Ravi Sharma eligible for the Half Marathon Training Programme Batch 2026B?"
SUNDAY = "How many volunteers confirmed for the Sunday long run, and who is the lead?"


class FakeAnswerLLM:
    """Answers YES citing the first two sources and the labels of every known conflict."""

    name = "fake"

    def __init__(self):
        self.prompts = []

    def generate_json(self, system, prompt):
        self.prompts.append((system, prompt))
        conflict_labels = re.findall(r"\[(S\d+)\]", prompt.split("KNOWN CONFLICTS", 1)[-1])
        return json.dumps({"verdict": "YES", "summary": "Eligible [S1][S2].",
                           "claims": [{"text": "Active member", "citations": ["S1"]},
                                      {"text": "Sources disagree", "citations": conflict_labels or ["S2"]}]})


def _bridge(case: str, monkeypatch) -> InfoBridge:
    monkeypatch.setattr(llm_module, "GeminiLLM", lambda *a, **k: FakeExtractionLLM())
    bridge = InfoBridge(backend="extractive", llm_extraction=True)
    bridge.ingest(DATA / case / "sources")
    return bridge


@pytest.fixture(scope="module")
def ravi():
    with pytest.MonkeyPatch.context() as mp:
        yield _bridge("case_03_conflict", mp)


@pytest.fixture(scope="module")
def sunday():
    with pytest.MonkeyPatch.context() as mp:
        yield _bridge("case_04_sunday_long_run", mp)


def test_ingest_stores_every_stage(ravi):
    assert any(f.extractor == "llm" for f in ravi.facts) and ravi.extraction_failed == []
    assert {"person:ravi-sharma", "person:ravi-shankar", "programme:hmtp-2026b"} <= {e.entity_id for e in ravi.entities}
    assert {c.attribute for c in ravi.conflicts} == {"medical_clearance_date", "batch_start_date"}
    assert ravi.store.graph is not None and len(ravi.store.vectors) == len(ravi.chunks)
    assert len(ravi.store.sql.conflicts(status="open")) == 2


def test_full_answer_carries_conflicts_entities_and_confidence(ravi):
    answer = ravi.ask(RAVI)
    assert answer.mode == "full" and answer.entities == ["person:ravi-sharma", "programme:hmtp-2026b"]
    assert {c.attribute for c in answer.conflicts} == {"medical_clearance_date", "batch_start_date"}
    ids = {r.chunk.chunk_id for r in answer.retrieved}
    assert {"members.csv#row=5", "registrations.csv#row=3"} <= ids
    assert not {"members.csv#row=4", "registrations.csv#row=5"} & ids  # Ravi Shankar
    for c in answer.conflicts:  # both sides of every conflict can be cited
        assert all(v.chunk_id in ids for v in c.values)
    batch = next(c for c in answer.conflicts if c.attribute == "batch_start_date")
    assert "registrations.csv#row=3" in {v.chunk_id for v in batch.values}  # Ravi's own row, not another person's
    assert answer.confidence == "medium" and "disagree" in answer.confidence_reason


def test_baseline_mode_is_the_v01_path(ravi):
    answer = ravi.ask(RAVI, mode="baseline")
    assert answer.mode == "baseline" and answer.conflicts == [] and answer.entities == []
    assert len(answer.retrieved) == ravi.top_k and all(r.channels == [] for r in answer.retrieved)
    with pytest.raises(ValueError):
        ravi.ask(RAVI, mode="other")


def test_prompt_has_known_conflicts_and_resolved_entities(ravi):
    llm = FakeAnswerLLM()
    ravi.synthesizer = LLMSynthesizer(llm)
    try:
        answer = ravi.ask(RAVI)
        baseline = ravi.ask(RAVI, mode="baseline")
    finally:
        ravi.synthesizer = InfoBridge(backend="extractive").synthesizer
    (system, prompt), (base_system, base_prompt) = llm.prompts
    labels = {r.chunk.chunk_id: f"S{r.rank}" for r in answer.retrieved}
    block = prompt.split("KNOWN CONFLICTS", 1)[1]
    line = next(l for l in block.splitlines() if l.startswith("K") and "medical_clearance_date of Ravi Sharma" in l)
    assert f'"2026-03-15" [{labels["members.csv#row=5"]}]' in line
    assert f'"22 June 2026" (= 2026-06-22) [{labels["whatsapp_coach_group.txt#msg=3"]}]' in line
    assert '"R. Sharma"' in prompt.split("RESOLVED ENTITIES", 1)[1]
    assert "Ravi Shankar" not in prompt
    assert "KNOWN CONFLICTS" in system and "KNOWN CONFLICTS" not in base_system + base_prompt
    assert answer.verdict == "YES" and not any(c.unsupported for c in answer.claims)
    assert answer.backend == "rag/fake" and baseline.backend == "rag-baseline/fake"


def test_demo_question_flags_the_count_conflict_first(sunday):
    answer = sunday.ask(SUNDAY)
    assert answer.entities == ["event:sunday-long-run"]
    count = answer.conflicts[0]
    assert count.attribute == "volunteer_count" and {v.value for v in count.values} == {"14", "12"}
    assert answer.confidence == "medium"
    assert answer.confidence_reason.startswith("Two sources disagree on the volunteer count of Sunday Long Run (14 vs 12)")
    retrieved = {r.chunk.chunk_id for r in answer.retrieved}
    assert {"sunday_long_run_plan.pdf#page=1&para=2", "whatsapp_run_coordinators.txt#msg=5"} <= retrieved  # lead, count
