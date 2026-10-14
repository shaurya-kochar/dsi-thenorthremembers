"""Issue #1: dataset size, split and privacy checks."""

import json
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"
GOLDS = {p.parent.name: json.loads(p.read_text()) for p in sorted((DATA / "synthetic").glob("case_*/gold.json"))}


def test_dataset_size():
    files = [f for case in (DATA / "synthetic").glob("case_*/sources") for f in case.iterdir()
             if not f.name.startswith("public_")]
    assert 15 <= len(files) <= 20
    assert 100 <= sum(len(g["entities"]) for g in GOLDS.values()) <= 150
    assert 25 <= sum(len(g["conflicts"]) for g in GOLDS.values()) <= 30


def test_split_is_about_70_30_and_complete():
    split = json.loads((DATA / "split.json").read_text())
    assert set(split["build"]) | set(split["held_out"]) == set(GOLDS)
    assert not set(split["build"]) & set(split["held_out"])
    held = sum(len(GOLDS[c]["conflicts"]) for c in split["held_out"])
    total = sum(len(g["conflicts"]) for g in GOLDS.values())
    assert 0.25 <= held / total <= 0.35
    for case, gold in GOLDS.items():
        assert gold["split"] == ("held_out" if case in split["held_out"] else "build")


def test_every_conflict_has_two_values_with_sources():
    for gold in GOLDS.values():
        for c in gold["conflicts"]:
            assert len({v["value"] for v in c["values"]}) >= 2, c
            assert all(v["sources"] for v in c["values"]), c


def test_synthetic_emails_use_reserved_domain():
    for case in ("case_04_sunday_long_run", "case_05_volunteer_attendance", "case_06_event_schedule"):
        for f in (DATA / "synthetic" / case / "sources").glob("*.*"):
            if f.suffix in (".csv", ".txt"):
                for word in f.read_text().split():
                    if "@" in word:
                        assert word.strip("<>,.").endswith("example.org"), (f.name, word)


def test_public_data_present():
    manifest = json.loads((DATA / "public" / "manifest.json").read_text())
    assert manifest["openalex"]["records"] == 200
    assert len(manifest["who"]) == 5
    assert all((DATA.parent / w["file"]).exists() for w in manifest["who"])
