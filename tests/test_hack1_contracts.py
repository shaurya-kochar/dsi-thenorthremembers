"""Hack 1 acceptance tests.

The fixture/schema checks pass now. The component tests are marked
``xfail(strict=True)``: they fail with NotImplementedError until the Hack 1
task lands, and pytest reports an error if one starts passing while still
marked, so remove the marker as each task is finished.

    Task A: test_extractor_maps_table_rows
    Task B: test_resolver_*
    Task C: test_conflict_detector_*
"""

import json
from pathlib import Path

import pandas as pd
import pytest

from infobridge.conflicts import ConflictDetector
from infobridge.extraction import InformationExtractor
from infobridge.ingestion import load_directory
from infobridge.models import Entity, Fact
from infobridge.resolution import EntityResolver
from infobridge.schema import ATTRIBUTES, TABLE_SCHEMAS

ROOT = Path(__file__).resolve().parents[1]
CASE3 = ROOT / "data" / "synthetic" / "case_03_conflict" / "sources"
FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "case_03_hack1.json").read_text())
FACTS = [Fact(**f) for f in FIXTURE["facts"]]
ENTITIES = [Entity(**e) for e in FIXTURE["entities"]]

hack1 = lambda task: pytest.mark.xfail(raises=NotImplementedError, strict=True, reason=f"Hack 1 {task}")


# ------------------------------------------------------------- pass today


def test_fixture_matches_dataset():
    _, chunks = load_directory(CASE3)
    by_id = {c.chunk_id: c.text.lower() for c in chunks}
    for f in FACTS:
        assert f.chunk_id in by_id, f
        assert f.attribute in ATTRIBUTES, f
    for e in ENTITIES:
        for m in e.mentions:
            assert m.text.lower() in by_id[m.chunk_id], m


def test_table_schemas_match_headers():
    for case in (ROOT / "data" / "synthetic").glob("case_*/sources"):
        for path in case.iterdir():
            if path.name not in TABLE_SCHEMAS:
                continue
            schema = TABLE_SCHEMAS[path.name]
            df = pd.read_csv(path, dtype=str) if path.suffix == ".csv" else pd.read_excel(path, dtype=str)
            assert schema.entity_column in df.columns
            assert set(schema.columns) <= set(df.columns), path.name
            assert set(schema.columns.values()) <= set(ATTRIBUTES), path.name


# ------------------------------------------------------- Task A: extractor


def test_extractor_maps_table_rows():
    _, chunks = load_directory(CASE3)
    facts = InformationExtractor().extract(chunks)
    got = {(f.entity_mention, f.attribute, f.value, f.chunk_id) for f in facts}
    for f in FACTS:
        if f.extractor == "csv_schema":
            assert (f.entity_mention, f.attribute, f.value, f.chunk_id) in got, f


# ------------------------------------------------- Task B: entity resolver


def _cluster_of(entities: list[Entity], text: str, chunk_id: str) -> set[tuple[str, str]]:
    for e in entities:
        mentions = {(m.text, m.chunk_id) for m in e.mentions}
        if (text, chunk_id) in mentions:
            return mentions
    raise AssertionError(f"mention {text!r} @ {chunk_id} not in any entity")


def test_resolver_merges_name_variants():
    entities = EntityResolver().resolve(FACTS)
    ravi = _cluster_of(entities, "Ravi Sharma", "members.csv#row=5")
    assert ("R. Sharma", "registrations.csv#row=3") in ravi  # phone match
    assert ("Ravi S.", "whatsapp_coach_group.txt#msg=3") in ravi  # truncated surname


def test_resolver_keeps_lookalikes_apart():
    entities = EntityResolver().resolve(FACTS)
    ravi = _cluster_of(entities, "Ravi Sharma", "members.csv#row=5")
    assert not any(text == "Ravi Shankar" for text, _ in ravi)


# ----------------------------------------------- Task C: conflict detector


@hack1("Task C")
def test_conflict_detector_finds_planted_conflicts():
    conflicts = ConflictDetector().detect(ENTITIES, FACTS)
    found = {(c.entity_id, c.attribute, frozenset(v.value for v in c.values)) for c in conflicts}
    expected = {(c["entity_id"], c["attribute"], frozenset(c["values"])) for c in FIXTURE["expected_conflicts"]}
    assert found == expected  # both found, and nothing else (e.g. same deadline in two sources is not a conflict)


@hack1("Task C")
def test_conflict_values_keep_their_sources():
    conflicts = ConflictDetector().detect(ENTITIES, FACTS)
    clearance = next(c for c in conflicts if c.attribute == "medical_clearance_date")
    sources = {v.value: v.chunk_id for v in clearance.values}
    assert sources["2026-03-15"] == "members.csv#row=5"
    assert sources["2026-06-22"] == "whatsapp_coach_group.txt#msg=3"
