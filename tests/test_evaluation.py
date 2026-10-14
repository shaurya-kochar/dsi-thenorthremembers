"""Issue #10: the new evaluation metrics, the split report and the before/after table (offline)."""

from infobridge.evaluation import aggregate, before_after, conflict_scores, run, score_query, summarise
from infobridge.models import Answer, Chunk, Claim, Conflict, ConflictValue, RetrievedChunk


def _retrieved(*chunk_ids):
    return [RetrievedChunk(chunk=Chunk(chunk_id=c, doc_id=c.split("#")[0], locator=c.split("#")[1], text=c),
                           score=0.5, rank=i) for i, c in enumerate(chunk_ids, start=1)]


GOLD = {"case_id": "t", "split": "held_out",
        "facts": [{"id": "F1", "entity_any": [], "value_any": ["vikram"], "sources": ["plan.pdf#para=2"]},
                  {"id": "F2", "entity_any": [], "value_any": ["14", "12"], "sources": ["plan.pdf#para=5", "chat#msg=5"]}],
        "conflicts": [{"id": "C1", "attribute": "volunteer_count", "values": [
            {"value": "14", "surface_any": ["14"], "sources": ["plan.pdf#para=5"]},
            {"value": "12", "surface_any": ["12"], "sources": ["chat#msg=5"]}]},
            {"id": "C2", "attribute": "start_time", "values": [
                {"value": "05:15", "surface_any": [], "sources": []}, {"value": "05:30", "surface_any": [], "sources": []}]}]}
QUERY = {"query_id": "q1", "fact_ids": ["F1", "F2"], "conflict_ids": ["C1"], "expected_verdict": None}


def _conflict(attribute, *values):
    return Conflict(conflict_id="C9", entity_id="event:x", attribute=attribute,
                    values=[ConflictValue(value=v, raw_value=v, chunk_id="x#row=1") for v in values])


def test_citation_correctness_is_per_stated_fact():
    answer = Answer(question="q", summary="", retrieved=_retrieved("plan.pdf#para=2", "plan.pdf#para=5", "chat#msg=5",
                                                                    "other#row=3"),
                    claims=[Claim(text="Vikram leads", citations=["S1", "S4"]),  # S4 is not a source of F1
                            Claim(text="14 vs 12 confirmed", citations=["S2", "S3"]),
                            Claim(text="Thanks everyone", citations=["S4"])])  # states no fact: not counted
    row = score_query(answer, QUERY, GOLD)
    assert row["citation_correctness"] == 0.75 and row["split"] == "held_out"


def test_fallback_counts_as_uncertain():
    answer = Answer(question="q", summary="Not enough evidence.", fallback=True)
    row = score_query(answer, {**QUERY, "expected_verdict": "UNCERTAIN", "fact_ids": []}, GOLD)
    assert row["verdict_accuracy"] == 1.0 and row["verdict"] == "UNCERTAIN"


def test_conflict_precision_and_recall_over_every_planted_conflict():
    flagged = [_conflict("volunteer_count", "14", "12"), _conflict("phone", "1", "2")]
    scores = conflict_scores(flagged, GOLD)
    assert (scores["conflict_precision"], scores["conflict_recall_all"]) == (0.5, 0.5)
    assert scores["missed_conflicts"] == ["C2"]
    assert conflict_scores([], GOLD)["conflict_precision"] is None


def test_aggregate_pools_conflicts_and_reports_splits():
    cases = [{"split": "build", "er_f1": 1.0, "flagged": 1, "true_flags": 1, "planted": 9, "caught": 1},
             {"split": "build", "er_f1": 0.9, "flagged": 0, "true_flags": 0, "planted": 0, "caught": 0},
             {"split": "held_out", "er_f1": 0.8, "flagged": 4, "true_flags": 3, "planted": 4, "caught": 3}]
    rows = [{"split": "build", "retrieval_recall": 1.0}, {"split": "held_out", "retrieval_recall": 0.5}]
    summary = summarise(rows, cases)
    assert summary["build"]["er_f1"] == 0.95 and summary["build"]["conflict_recall_all"] == round(1 / 9, 3)
    assert summary["held_out"]["conflict_precision"] == 0.75 and summary["held_out"]["questions"] == 1
    assert summary["all"]["conflict_precision"] == 0.8
    assert aggregate([], [cases[1]])["conflict_precision"] == 1.0  # nothing flagged where nothing is planted


def test_eval_run_and_before_after_table(tmp_path):
    data = __import__("pathlib").Path(__file__).resolve().parents[1] / "data" / "synthetic"
    only = ["case_03_conflict", "case_07_race_day_logistics"]
    full = run(data, "extractive", "f", out_dir=tmp_path, mode="full", only=only)
    base = run(data, "extractive", "b", out_dir=tmp_path, mode="baseline", only=only)
    assert {c["case_id"] for c in full["cases"]} == set(only) and base["cases"] == []
    assert full["summary"]["held_out"]["er_f1"] == 1.0 and full["summary"]["build"]["questions"] == 1
    import json

    table = before_after(json.loads((tmp_path / "b.json").read_text()), json.loads((tmp_path / "f.json").read_text()))
    case3 = next(l for l in table.splitlines() if l.startswith("| Retrieval recall (case 3)"))
    assert case3.split(" | ")[1:3] == ["0.57", "1.00"]  # the Sprint 2 baseline vs hybrid retrieval
    assert "| Entity resolution F1 | – | 1.00 | – | 1.00 |" in table
    assert (tmp_path / "f.md").read_text().count("### Per case") == 1
