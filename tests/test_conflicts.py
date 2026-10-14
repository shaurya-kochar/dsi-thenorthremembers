"""Issue #6: conflict detector on every case (offline: rules only, or a fake LLM for chat/PDF facts)."""

import json
import re
from pathlib import Path

import pytest

from infobridge.conflicts import ConflictDetector, severity_of
from infobridge.extraction import InformationExtractor
from infobridge.ingestion import load_directory
from infobridge.llm_extraction import LLMFactExtractor
from infobridge.resolution import EntityResolver

DATA = Path(__file__).resolve().parents[1] / "data" / "synthetic"
CASES = sorted(p.name for p in DATA.glob("case_*"))


class FakeLLM:
    """Returns the facts Gemini finds in the chat and plan of case_04 / case_03; the chunk
    label is looked up by the text it holds, so the fake does not depend on chunk numbering."""

    FACTS = {
        "sunday_long_run_plan.pdf": [
            ("Volunteers confirmed: 14", "Sunday Long Run", "event", "volunteer_count", "14"),
            ("flag-off at 5:15 AM", "Sunday Long Run", "event", "start_time", "5:15 AM"),
        ],
        "whatsapp_run_coordinators.txt": [
            ("we have 12 confirmed", "Sunday Long Run", "event", "volunteer_count", "12 confirmed"),
            ("Flag-off at 5:30 sharp", "Sunday Long Run", "event", "start_time", "5:30"),
            ("I have to drop out", "Kavya", "person", "signup_status", "drop out"),
        ],
        "whatsapp_coach_group.txt": [
            ("22 June 2026", "Ravi S.", "person", "medical_clearance_date", "22 June 2026"),
        ],
        "programme_rules.pdf": [
            ("8 November 2026", "Batch 2026B", "programme", "batch_start_date", "8 November 2026"),
        ],
    }

    def generate_json(self, system, prompt, retries=3):
        doc = re.search(r"Chunks from (\S+):", prompt)[1]
        facts = []
        for text, entity, etype, attribute, value in self.FACTS.get(doc, []):
            label = re.search(rf"\[(C\d+)\][^\n]*{re.escape(text)}", prompt)[1]
            facts.append({"chunk": label, "entity": entity, "entity_type": etype, "attribute": attribute,
                          "value": value})
        return json.dumps({"facts": facts})


def detect(case: str, llm=None):
    _, chunks = load_directory(DATA / case / "sources")
    text_extractor = LLMFactExtractor(llm) if llm else None
    facts = InformationExtractor(text_extractor).extract(chunks)
    entities = EntityResolver().resolve(facts)
    return ConflictDetector().detect(entities, facts, {c.chunk_id: c for c in chunks})


def gold_conflicts(case: str) -> dict[tuple[str, frozenset], dict]:
    gold = json.loads((DATA / case / "gold.json").read_text())
    return {(c["attribute"], frozenset(v["value"] for v in c["values"])): c for c in gold["conflicts"]}


def key(conflict) -> tuple[str, frozenset]:
    return conflict.attribute, frozenset(v.value for v in conflict.values)


@pytest.mark.parametrize("case", CASES)
def test_every_flagged_conflict_is_planted(case):
    """Precision without the LLM: whatever the rules find must be in the answer key."""
    gold = gold_conflicts(case)
    for c in detect(case):
        assert key(c) in gold, c


def test_no_conflicts_in_cases_without_planted_ones():
    assert detect("case_01_simple") == [] and detect("case_02_medium") == []


def test_name_spellings_are_flagged_with_their_sources():
    found = {key(c): c for c in detect("case_05_volunteer_attendance")}
    laxmi = found[("full_name", frozenset({"Laxmi Prasad", "Lakshmi Prasad"}))]
    assert {v.value: v.chunk_id for v in laxmi.values} == {"Laxmi Prasad": "attendance_log.csv#row=3",
                                                           "Lakshmi Prasad": "night_run_report.txt#para=2"}
    assert laxmi.severity == "low"
    assert ("full_name", frozenset({"Rekha Pillai", "Rekha Pilai"})) in {key(c) for c in detect("case_07_race_day_logistics")}
    # 'S. Kiran', 'I. Siddiqui' (initials) are ways of writing a name, not a second spelling
    case4 = [c for c in detect("case_04_sunday_long_run") if c.attribute == "full_name"]
    assert [key(c) for c in case4] == [("full_name", frozenset({"Bhargavi Kulkarni", "Bhargvi Kulkarni"}))]
    bhargavi = case4[0]
    assert next(v for v in bhargavi.values if v.value == "Bhargavi Kulkarni").chunk_id == "volunteer_signups.xlsx#row=10"
    assert "Bhargavi Kulkarni" in bhargavi.suggestion  # the sheet and the chat agree


def test_demo_case_conflicts_from_chat_and_plan():
    found = {key(c): c for c in detect("case_04_sunday_long_run", FakeLLM())}
    gold = gold_conflicts("case_04_sunday_long_run")
    count = ("volunteer_count", frozenset({"14", "12"}))
    for k in [count, ("start_time", frozenset({"05:15", "05:30"})),
              ("signup_status", frozenset({"Confirmed", "Withdrawn"}))]:
        assert k in found and k in gold, k
    assert set(found) <= set(gold)  # nothing that is not planted
    by_value = {v.value: v.chunk_id for v in found[count].values}
    assert by_value == {"14": "sunday_long_run_plan.pdf#page=1&para=5", "12": "whatsapp_run_coordinators.txt#msg=5"}
    assert found[count].entity_id == "event:sunday-long-run" and found[count].severity == "medium"
    assert "whatsapp_run_coordinators.txt" in found[count].suggestion  # the chat count is the later one
    assert found[("start_time", frozenset({"05:15", "05:30"}))].severity == "high"
    kavya = found[("signup_status", frozenset({"Confirmed", "Withdrawn"}))]
    assert kavya.entity_id == "person:kavya-reddy"
    assert {v.raw_value for v in kavya.values} == {"Confirmed", "drop out"}


def test_case3_finds_c1_and_c2_with_suggestions():
    conflicts = detect("case_03_conflict", FakeLLM())
    assert {(c.entity_id, *key(c)) for c in conflicts} == {
        ("person:ravi-sharma", "medical_clearance_date", frozenset({"2026-03-15", "2026-06-22"})),
        ("programme:hmtp-2026b", "batch_start_date", frozenset({"2026-11-01", "2026-11-08"}))}
    clearance, batch = sorted(conflicts, key=lambda c: c.attribute)[::-1]
    assert "most recent" in clearance.suggestion and "whatsapp_coach_group.txt" in clearance.suggestion
    assert "official document (programme_rules.pdf" in batch.suggestion
    assert set(next(v for v in batch.values if v.value == "2026-11-01").sources) >= {
        "registrations.csv#row=3", "registrations.csv#row=5"}
    assert [c.conflict_id for c in conflicts] == ["C1", "C2"]


def test_severity_rule():
    assert [severity_of(a) for a in ("start_time", "batch_start_date", "volunteer_count", "phone", "full_name")] == \
        ["high", "medium", "medium", "low", "low"]
