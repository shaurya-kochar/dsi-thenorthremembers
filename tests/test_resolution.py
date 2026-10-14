"""Issue #3: entity resolution on every case."""

import json
from pathlib import Path

import pytest

from infobridge.evaluation import entity_resolution_f1
from infobridge.extraction import InformationExtractor
from infobridge.ingestion import load_directory
from infobridge.resolution import EntityResolver, name_tokens, names_compatible

DATA = Path(__file__).resolve().parents[1] / "data" / "synthetic"
CASES = sorted(DATA.glob("case_*"))


def _entities(case: Path):
    _, chunks = load_directory(case / "sources")
    return EntityResolver().resolve(InformationExtractor().extract(chunks))


@pytest.mark.parametrize("case", CASES, ids=lambda p: p.name)
def test_entity_resolution_f1(case):
    gold = json.loads((case / "gold.json").read_text())
    assert entity_resolution_f1(_entities(case), gold)["f1"] >= 0.85


def _together(entities, a: str, b: str) -> bool:
    return any({a, b} <= {m.text for m in e.mentions} for e in entities)


def test_lookalikes_stay_apart():
    case4 = _entities(DATA / "case_04_sunday_long_run")
    assert not _together(case4, "Kavya Reddy", "Kavitha Reddy")
    assert not _together(case4, "Rohit Varma", "Rohith Verma")  # two sheet records, different phones
    assert not _together(case4, "Sai Kiran", "Sai Krishna")
    assert not _together(_entities(DATA / "case_05_volunteer_attendance"), "Harish Kumar", "Harsha Kumar")
    assert not _together(_entities(DATA / "case_02_medium"), "Srinivas Rao Kumar", "Srinivas Reddy")


def test_short_forms_and_spellings_join_the_right_person():
    case4 = _entities(DATA / "case_04_sunday_long_run")
    assert _together(case4, "Vikram Rao", "Vikram anna")
    assert _together(case4, "Bhargavi Kulkarni", "Bhargvi Kulkarni")
    assert _together(case4, "Sai Kiran", "S. Kiran")
    assert _together(_entities(DATA / "case_05_volunteer_attendance"), "Laxmi Prasad", "Lakshmi Prasad")
    case2 = _entities(DATA / "case_02_medium")
    assert _together(case2, "Srinivas Rao Kumar", "Srini")  # decided by the shared station (AS3)
    assert _together(case2, "Mohammed Farhan", "Farhan bhai")


def test_every_merge_is_explained():
    for e in _entities(DATA / "case_03_conflict"):
        if len({m.text for m in e.mentions}) > 1:
            assert e.match_evidence, e.entity_id


def test_name_rules():
    t = name_tokens
    assert names_compatible(t("S. R. Kumar"), t("Srinivas Rao Kumar"))
    assert not names_compatible(t("Ravi Sharma"), t("Ravi Shankar"))
    assert names_compatible(t("Laxmi Prasad"), t("Lakshmi Prasad"))
    assert not names_compatible(t("Harish Kumar"), t("Harsha Kumar"))
