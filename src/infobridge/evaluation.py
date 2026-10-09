"""Evaluation harness — scores answers against each case's ``gold.json``.

Automated metrics (v0.1):
  retrieval_recall      share of gold facts with ≥1 gold source chunk in the top-k
  fact_recall           share of gold facts stated in the answer (synthesis completeness)
  citation_validity     share of cited labels that point to a real retrieved chunk
  citation_accuracy     of the facts stated, share whose claim cites a gold source chunk
  unsupported_claims    share of claims with no valid citation
  conflict_recall_text  share of planted conflicts where the answer states both sides
  conflict_recall       share of planted conflicts in Answer.conflicts (structured; 0 until Hack 1)
  verdict_accuracy      exact match of YES/NO/UNCERTAIN, where the gold has one
  latency_s

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

from .models import Answer, Entity

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

    ratio = lambda num, den: round(num / den, 3) if den else None
    return {
        "case_id": gold["case_id"],
        "query_id": query["query_id"],
        "retrieval_recall": ratio(sum(bool(set(f["sources"]) & retrieved_ids) for f in facts), len(facts)),
        "fact_recall": ratio(len(covered), len(facts)),
        "citation_validity": ratio(sum(l in valid_labels for l in all_labels), len(all_labels)),
        "citation_accuracy": ratio(len(correctly_cited), len(covered)),
        "unsupported_claims": ratio(sum(c.unsupported for c in answer.claims), len(answer.claims)),
        "conflict_recall_text": ratio(sum(both_sides(c) for c in conflicts), len(conflicts)),
        "conflict_recall": ratio(sum(structured_hit(c) for c in conflicts), len(conflicts)),
        "verdict_accuracy": (None if query["expected_verdict"] is None
                             else float(answer.verdict == query["expected_verdict"])),
        "latency_s": answer.latency_s,
        "missed_facts": [f["id"] for f in facts if f not in covered],
        "fallback": answer.fallback,
    }


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


METRICS = ["retrieval_recall", "fact_recall", "citation_validity", "citation_accuracy",
           "unsupported_claims", "conflict_recall_text", "conflict_recall", "verdict_accuracy", "latency_s"]


def aggregate(rows: list[dict]) -> dict:
    out = {}
    for m in METRICS:
        vals = [r[m] for r in rows if r[m] is not None]
        out[m] = round(mean(vals), 3) if vals else None
    return out


HEADERS = {"case_id": "Case", "retrieval_recall": "Retr. recall", "fact_recall": "Fact recall",
           "citation_validity": "Cit. validity", "citation_accuracy": "Cit. accuracy",
           "unsupported_claims": "Unsupported", "conflict_recall_text": "Conflict (text)",
           "conflict_recall": "Conflict (struct.)", "verdict_accuracy": "Verdict", "latency_s": "Latency (s)"}


def to_markdown(rows: list[dict], summary: dict, title: str) -> str:
    cols = ["case_id"] + METRICS
    fmt = lambda v: "–" if v is None else (f"{v:.2f}" if isinstance(v, float) else str(v))
    lines = [f"## {title}", "", "| " + " | ".join(HEADERS[c] for c in cols) + " |", "|" + "---|" * len(cols)]
    for r in rows:
        lines.append("| " + " | ".join(fmt(r[c]) for c in cols) + " |")
    lines.append("| **mean** | " + " | ".join(fmt(summary[m]) for m in METRICS) + " |")
    lines += ["", "Missed facts: " + "; ".join(f"{r['case_id']}: {r['missed_facts'] or 'none'}" for r in rows)]
    return "\n".join(lines) + "\n"


def run(data_dir: str | Path, backend: str, tag: str, out_dir: str | Path = "results") -> dict:
    from .pipeline import InfoBridge

    rows, answers = [], []
    for case_dir, gold in load_cases(data_dir):
        bridge = InfoBridge(backend=backend)
        bridge.ingest(case_dir / "sources")
        for query in gold["queries"]:
            answer = bridge.ask(query["question"])
            rows.append(score_query(answer, query, gold))
            answers.append({"case_id": gold["case_id"], "query_id": query["query_id"], "answer": answer.model_dump(mode="json")})

    summary = aggregate(rows)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{tag}.json").write_text(json.dumps({"tag": tag, "backend": backend, "summary": summary,
                                                  "per_query": rows, "answers": answers}, indent=2))
    (out / f"{tag}.md").write_text(to_markdown(rows, summary, f"{tag} ({backend})"))
    return {"summary": summary, "rows": rows}
