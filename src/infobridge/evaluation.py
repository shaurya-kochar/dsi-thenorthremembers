"""Evaluation harness — scores answers against each case's ``gold.json``.

Per question:
  retrieval_recall      share of gold facts with ≥1 gold source chunk in the top-k
  fact_recall           share of gold facts stated in the answer (synthesis completeness)
  citation_validity     share of cited labels that point to a real retrieved chunk
  citation_accuracy     of the facts stated, share whose claim cites a gold source chunk
  citation_correctness  of the chunks cited next to a stated fact, share that are a gold source of that
                        fact (or of a side of a planted conflict): file + row + field level, since a
                        chunk is one row / message / paragraph (issue #10)
  unsupported_claims    share of claims with no valid citation
  conflict_recall_text  share of planted conflicts where the answer states both sides
  conflict_recall       share of the question's planted conflicts in Answer.conflicts (structured)
  verdict_accuracy      exact match of YES/NO/UNCERTAIN, where the gold has one (a fallback = UNCERTAIN)
  latency_s
Per case (issue #10), full pipeline only:
  er_f1                 entity-resolution pairwise F1 against the gold entities
  conflict_precision    flagged conflicts that are planted (same field, gold values among the flagged
                        ones) / all flagged
  conflict_recall_all   planted conflicts caught / all planted conflicts of the case (not only the
                        question's)
Build and held-out cases (``split``) are reported separately.

Fact/conflict matching is keyword-based (gold lists accepted surface forms per
fact), which is cheap and reproducible but can miss paraphrases — a known
limitation; an LLM-judge or manual check is the planned complement.
"""

from __future__ import annotations

import json
import re
from itertools import combinations
from pathlib import Path
from statistics import mean

from .models import Answer, Conflict, Entity

LABEL = re.compile(r"\[(S\d+)\]")


def _norm(text: str) -> str:
    text = text.lower().replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", text)


def _units(answer: Answer) -> list[tuple[str, set[str]]]:
    """Answer split into (text, cited chunk_ids) units: each claim + each summary sentence."""
    by_label = {f"S{r.rank}": r.chunk.chunk_id for r in answer.retrieved}
    units = [(_norm(c.text), {by_label[l] for l in c.citations if l in by_label}) for c in answer.claims]
    for sentence in re.split(r"(?<=[.!?])\s+", answer.summary):
        if sentence.strip():
            units.append((_norm(sentence), {by_label[l] for l in LABEL.findall(sentence) if l in by_label}))
    return units


def _fact_units(fact: dict, units: list[tuple[str, set[str]]]) -> list[tuple[str, set[str]]]:
    def has(text: str, options: list[str]) -> bool:
        return not options or any(o.lower() in text for o in options)

    return [u for u in units if has(u[0], fact["entity_any"]) and has(u[0], fact["value_any"])]


def score_query(answer: Answer, query: dict, gold: dict) -> dict:
    facts = [f for f in gold["facts"] if f["id"] in query["fact_ids"]]
    conflicts = [c for c in gold["conflicts"] if c["id"] in query["conflict_ids"]]
    retrieved_ids = {r.chunk.chunk_id for r in answer.retrieved}
    units = _units(answer)
    full_text = _norm(answer.summary + " " + " ".join(c.text for c in answer.claims))

    stated = {f["id"]: _fact_units(f, units) for f in facts}
    covered = [f for f in facts if stated[f["id"]]]
    correctly_cited = [f for f in covered if any(set(f["sources"]) & cited for _, cited in stated[f["id"]])]

    all_labels = [l for c in answer.claims for l in c.citations]
    valid_labels = {f"S{r.rank}" for r in answer.retrieved}

    def both_sides(c: dict) -> bool:
        return sum(any(s in full_text for s in v["surface_any"]) for v in c["values"]) >= 2

    def structured_hit(c: dict) -> bool:
        gold_values = {v["value"] for v in c["values"]}
        return any(gold_values <= {v.value for v in pred.values} for pred in answer.conflicts)

    # citation correctness: chunks cited next to a stated fact must be that fact's sources
    conflict_sources = {s for c in conflicts for v in c["values"] for s in v["sources"]}
    cited, correct = 0, 0
    for unit in units:
        stated_here = [f for f in facts if unit in stated[f["id"]]]
        if stated_here and unit[1]:
            allowed = set().union(*(set(f["sources"]) for f in stated_here)) | conflict_sources
            cited += len(unit[1])
            correct += len(unit[1] & allowed)

    verdict = "UNCERTAIN" if answer.fallback else answer.verdict
    ratio = lambda num, den: round(num / den, 3) if den else None
    return {
        "case_id": gold["case_id"],
        "query_id": query["query_id"],
        "retrieval_recall": ratio(sum(bool(set(f["sources"]) & retrieved_ids) for f in facts), len(facts)),
        "fact_recall": ratio(len(covered), len(facts)),
        "citation_validity": ratio(sum(l in valid_labels for l in all_labels), len(all_labels)),
        "citation_accuracy": ratio(len(correctly_cited), len(covered)),
        "citation_correctness": ratio(correct, cited),
        "unsupported_claims": ratio(sum(c.unsupported for c in answer.claims), len(answer.claims)),
        "conflict_recall_text": ratio(sum(both_sides(c) for c in conflicts), len(conflicts)),
        "conflict_recall": ratio(sum(structured_hit(c) for c in conflicts), len(conflicts)),
        "verdict_accuracy": (None if query["expected_verdict"] is None
                             else float(verdict == query["expected_verdict"])),
        "verdict": verdict,
        "latency_s": answer.latency_s,
        "missed_facts": [f["id"] for f in facts if f not in covered],
        "fallback": answer.fallback,
        "split": gold.get("split", "build"),
    }


def conflict_scores(flagged: list[Conflict], gold: dict) -> dict:
    """Detector precision / recall for one case against every planted conflict."""
    planted = [(c["attribute"], {v["value"] for v in c["values"]}) for c in gold["conflicts"]]

    def match(pred: Conflict, attribute: str, values: set[str]) -> bool:
        return pred.attribute == attribute and values <= {v.value for v in pred.values}

    true_flags = sum(any(match(p, *g) for g in planted) for p in flagged)
    caught = sum(any(match(p, *g) for p in flagged) for g in planted)
    return {"flagged": len(flagged), "true_flags": true_flags, "planted": len(planted), "caught": caught,
            "conflict_precision": round(true_flags / len(flagged), 3) if flagged else None,
            "conflict_recall_all": round(caught / len(planted), 3) if planted else None,
            "missed_conflicts": [gold["conflicts"][i]["id"] for i, g in enumerate(planted)
                                 if not any(match(p, *g) for p in flagged)]}


def entity_resolution_f1(predicted: list[Entity], gold: dict) -> dict:
    """Pairwise F1 over (mention text, chunk_id) pairs — for Hack 1's resolver."""

    def pairs(clusters: list[set[tuple[str, str]]]) -> set[frozenset]:
        return {frozenset(p) for cl in clusters for p in combinations(sorted(cl), 2)}

    gold_clusters = [{(m["text"], m["chunk_id"]) for m in e["mentions"]} for e in gold["entities"]]
    gold_mentions = set().union(*gold_clusters) if gold_clusters else set()
    pred_clusters = [{(m.text, m.chunk_id) for m in e.mentions} & gold_mentions for e in predicted]
    g, p = pairs(gold_clusters), pairs(pred_clusters)
    tp = len(g & p)
    precision = tp / len(p) if p else 0.0
    recall = tp / len(g) if g else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": round(precision, 3), "recall": round(recall, 3), "f1": round(f1, 3)}


def load_cases(data_dir: str | Path) -> list[tuple[Path, dict]]:
    return [(p.parent, json.loads(p.read_text())) for p in sorted(Path(data_dir).glob("case_*/gold.json"))]


METRICS = ["retrieval_recall", "fact_recall", "citation_validity", "citation_accuracy", "citation_correctness",
           "unsupported_claims", "conflict_recall_text", "conflict_recall", "verdict_accuracy", "latency_s"]
CASE_METRICS = ["er_f1", "conflict_precision", "conflict_recall_all"]
SPLITS = ("build", "held_out")


def aggregate(rows: list[dict], cases: list[dict] | None = None) -> dict:
    """Mean of each question metric; ER F1 averaged over cases; conflict precision / recall pooled
    over the cases (micro), so a case with one conflict does not weigh as much as one with nine."""
    out = {}
    for m in METRICS:
        vals = [r[m] for r in rows if r.get(m) is not None]
        out[m] = round(mean(vals), 3) if vals else None
    cases = [c for c in cases or [] if c.get("er_f1") is not None]
    out["questions"] = len(rows)
    out["er_f1"] = round(mean(c["er_f1"] for c in cases), 3) if cases else None
    flagged, true_flags = sum(c["flagged"] for c in cases), sum(c["true_flags"] for c in cases)
    planted, caught = sum(c["planted"] for c in cases), sum(c["caught"] for c in cases)
    out["conflict_precision"] = round(true_flags / flagged, 3) if flagged else (1.0 if cases else None)
    out["conflict_recall_all"] = round(caught / planted, 3) if planted else None
    return out


def summarise(rows: list[dict], cases: list[dict]) -> dict:
    return {split: aggregate([r for r in rows if r["split"] == split], [c for c in cases if c["split"] == split])
            for split in SPLITS} | {"all": aggregate(rows, cases)}


HEADERS = {"case_id": "Case", "query_id": "Q", "retrieval_recall": "Retr. recall", "fact_recall": "Fact recall",
           "citation_validity": "Cit. validity", "citation_accuracy": "Cit. accuracy",
           "citation_correctness": "Cit. correct", "unsupported_claims": "Unsupported",
           "conflict_recall_text": "Conflict (text)", "conflict_recall": "Conflict (struct.)",
           "verdict_accuracy": "Verdict", "latency_s": "Latency (s)", "er_f1": "ER F1",
           "conflict_precision": "Conflict precision", "conflict_recall_all": "Conflicts caught"}


def _fmt(v) -> str:
    return "–" if v is None else (f"{v:.2f}" if isinstance(v, float) else str(v))


def to_markdown(rows: list[dict], summary: dict, title: str, cases: list[dict] | None = None) -> str:
    cols = ["case_id", "query_id"] + METRICS
    lines = [f"## {title}", "", "### Per question", "",
             "| " + " | ".join(HEADERS[c] for c in cols) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join(_fmt(r[c]) for c in cols) + " |" for r in rows]
    lines += ["", "### Summary", "", "| Split | Questions | " + " | ".join(HEADERS[m] for m in METRICS + CASE_METRICS)
              + " |", "|" + "---|" * (len(METRICS + CASE_METRICS) + 2)]
    for split in (*SPLITS, "all"):
        agg = summary[split]
        lines.append(f"| {split} | {agg['questions']} | " + " | ".join(_fmt(agg[m]) for m in METRICS + CASE_METRICS)
                     + " |")
    if cases:
        lines += ["", "### Per case", "", "| Case | Split | ER F1 | Flagged | Planted | Caught | Precision | "
                  "Missed conflicts |", "|---|---|---|---|---|---|---|---|"]
        lines += [f"| {c['case_id']} | {c['split']} | {_fmt(c['er_f1'])} | {c['flagged']} | {c['planted']} | "
                  f"{c['caught']} | {_fmt(c['conflict_precision'])} | {', '.join(c['missed_conflicts']) or '–'} |"
                  for c in cases]
    failing = [r for r in rows if (r["fact_recall"] or 0) < 1 and r["missed_facts"] or r["verdict_accuracy"] == 0.0]
    lines += ["", "### Failing questions", ""]
    lines += [f"- {r['case_id']} {r['query_id']}: missed facts {r['missed_facts'] or 'none'}"
              + (f"; verdict {r['verdict']}" if r["verdict_accuracy"] == 0.0 else "") for r in failing] or ["None."]
    return "\n".join(lines) + "\n"


def _ask(bridge, question: str, attempts: int = 4) -> Answer:
    """One question; a transient LLM error (503 / 429 on the free tier) is retried, not fatal to the run."""
    import time

    for attempt in range(attempts):
        try:
            return bridge.ask(question)
        except Exception:
            if attempt == attempts - 1:
                raise
            time.sleep(30 * (attempt + 1))


def run(data_dir: str | Path, backend: str, tag: str, out_dir: str | Path = "results", mode: str = "full",
        only: list[str] | None = None) -> dict:
    from .pipeline import InfoBridge

    rows, answers, cases = [], [], []
    for case_dir, gold in load_cases(data_dir):
        if only and gold["case_id"] not in only:
            continue
        # text facts only matter to the full pipeline; the baseline does not spend LLM calls on them
        bridge = InfoBridge(backend=backend, mode=mode, llm_extraction=None if mode == "full" else False)
        bridge.ingest(case_dir / "sources")
        split = gold.get("split", "build")
        if mode == "full":
            cases.append({"case_id": gold["case_id"], "split": split,
                          "er_f1": entity_resolution_f1(bridge.entities, gold)["f1"],
                          "extraction_failed": bridge.extraction_failed,
                          **conflict_scores(bridge.conflicts, gold)})
        for query in gold["queries"]:
            answer = _ask(bridge, query["question"])
            rows.append(score_query(answer, query, gold))
            answers.append({"case_id": gold["case_id"], "query_id": query["query_id"],
                            "answer": answer.model_dump(mode="json")})

    summary = summarise(rows, cases)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{tag}.json").write_text(json.dumps({"tag": tag, "backend": backend, "mode": mode, "summary": summary,
                                                 "per_case": cases, "per_query": rows, "answers": answers}, indent=2))
    (out / f"{tag}.md").write_text(to_markdown(rows, summary, f"{tag} ({mode}, {backend})", cases))
    return {"summary": summary, "rows": rows, "cases": cases}


# ------------------------------------------------------------- before / after

COMPARE = [  # (label, metric, where, target)
    ("Retrieval recall (case 3)", "retrieval_recall", "case_03_conflict", "≥ 0.90"),
    ("Retrieval recall", "retrieval_recall", None, ""),
    ("Fact recall", "fact_recall", None, ""),
    ("Structured conflict recall (per question)", "conflict_recall", None, "≥ 0.90"),
    ("Conflicts caught (all planted)", "conflict_recall_all", None, "≥ 0.90 build, ≥ 0.80 held-out"),
    ("Conflict precision", "conflict_precision", None, "≥ 0.80"),
    ("Conflicts stated in the answer text", "conflict_recall_text", None, ""),
    ("Entity resolution F1", "er_f1", None, "≥ 0.85"),
    ("Citation validity", "citation_validity", None, "1.00"),
    ("Citation correctness (file, row, field)", "citation_correctness", None, "≥ 0.90 held-out"),
    ("Citation accuracy", "citation_accuracy", None, ""),
    ("Unsupported claims", "unsupported_claims", None, "lower is better"),
    ("Verdict accuracy (case 3)", "verdict_accuracy", "case_03_conflict", "1.00"),
    ("Verdict accuracy", "verdict_accuracy", None, ""),
    ("Latency (s)", "latency_s", None, ""),
]


def before_after(before: dict, after: dict) -> str:
    """One table: rows = metrics, columns = baseline / full for the build and the held-out set."""
    def value(result: dict, metric: str, split: str, case: str | None):
        if case:
            rows = [r for r in result["per_query"] if r["case_id"] == case and r.get(metric) is not None]
            return round(mean(r[metric] for r in rows), 3) if rows else None
        return result["summary"].get(split, {}).get(metric)

    head = ("| Metric | Build: baseline | Build: full | Held-out: baseline | Held-out: full | Target |\n"
            "|---|---|---|---|---|---|")
    lines = [f"## Before / after: {before['tag']} → {after['tag']}", "",
             f"Baseline = Sprint 2 naive RAG (`--mode baseline`); full = Hack 1 pipeline (`--mode full`). "
             f"Backend: {after.get('backend')}. Build questions: {after['summary']['build']['questions']}, "
             f"held-out questions: {after['summary']['held_out']['questions']}. Case 3 rows are on the build set. "
             f"The baseline has no resolver or detector, so its ER F1 and conflict precision are '–' and its "
             f"conflicts caught are 0.", "", head]
    for label, metric, case, target in COMPARE:
        cells = []
        for split in SPLITS:
            for result in (before, after):
                if case and split == "held_out":
                    cells.append("")
                    continue
                v = value(result, metric, split, case)
                if v is None and metric == "conflict_recall_all" and result.get("mode") == "baseline":
                    v = 0.0
                cells.append(_fmt(v))
        lines.append(f"| {label} | " + " | ".join(cells) + f" | {target} |")
    return "\n".join(lines) + "\n"
