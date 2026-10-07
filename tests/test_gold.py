"""Integrity of the synthetic gold standard: every referenced chunk must exist."""

import json
from pathlib import Path

import pytest

from infobridge.ingestion import load_directory

DATA = Path(__file__).resolve().parents[1] / "data" / "synthetic"
CASES = sorted(DATA.glob("case_*"))


@pytest.mark.parametrize("case", CASES, ids=lambda p: p.name)
def test_gold_references_existing_chunks(case):
    gold = json.loads((case / "gold.json").read_text())
    _, chunks = load_directory(case / "sources")
    by_id = {c.chunk_id: c for c in chunks}

    refs = [s for f in gold["facts"] for s in f["sources"]]
    refs += [s for c in gold["conflicts"] for v in c["values"] for s in v["sources"]]
    missing = [r for r in refs if r not in by_id]
    assert not missing, f"gold references unknown chunks: {missing}"

    for e in gold["entities"]:
        for m in e["mentions"]:
            assert m["chunk_id"] in by_id, m
            assert m["text"].lower() in by_id[m["chunk_id"]].text.lower(), m


@pytest.mark.parametrize("case", CASES, ids=lambda p: p.name)
def test_queries_reference_defined_ids(case):
    gold = json.loads((case / "gold.json").read_text())
    fact_ids = {f["id"] for f in gold["facts"]}
    conflict_ids = {c["id"] for c in gold["conflicts"]}
    for q in gold["queries"]:
        assert set(q["fact_ids"]) <= fact_ids
        assert set(q["conflict_ids"]) <= conflict_ids
