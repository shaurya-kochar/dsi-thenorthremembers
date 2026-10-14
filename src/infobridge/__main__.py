"""Command line entry point.

    python -m infobridge ask  data/synthetic/case_03_conflict/sources "Is Ravi Sharma eligible for HMTP 2026B?"
    python -m infobridge eval --backend gemini --mode baseline --tag baseline_v0.1_rerun
    python -m infobridge eval --backend gemini --mode full --tag hack1_v0.1
    python -m infobridge compare --before baseline_v0.1_rerun --after hack1_v0.1   # results/before_after.md
    python -m infobridge trail data/synthetic/case_03_conflict/sources "Is Ravi Sharma eligible ...?"
    python -m infobridge ask --mode baseline ...   # the v0.1 naive-RAG path, for the before/after comparison
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .evaluation import before_after, run, to_markdown
from .models import Answer
from .pipeline import InfoBridge
from .provenance import answer_trail


def render(answer: Answer) -> str:
    lines = []
    if answer.fallback:
        lines.append("⚠  FALLBACK (assisted search)")
    if answer.verdict:
        lines.append(f"VERDICT: {answer.verdict}")
    lines += [answer.summary, ""]
    if answer.claims:
        lines.append("Claims:")
        for c in answer.claims:
            flag = "  ✗ unsupported" if c.unsupported else ""
            lines.append(f"  - {c.text} {' '.join(f'[{l}]' for l in c.citations)}{flag}")
        lines.append("")
    lines.append("Sources used:")
    for cit in answer.citations:
        lines.append(f"  [{cit.label}] {cit.doc_id} @ {cit.locator}")
    lines.append(f"Conflicts flagged: {len(answer.conflicts)}")
    for c in answer.conflicts:
        sides = " vs ".join(f"{v.raw_value!r} ({v.chunk_id})" for v in c.values)
        lines.append(f"  {c.conflict_id} [{c.severity}] {c.attribute} of {c.entity_name or c.entity_id}: {sides}")
        if c.suggestion:
            lines.append(f"      suggestion: {c.suggestion}")
    if answer.confidence:
        lines.append(f"Confidence: {answer.confidence.upper()} - {answer.confidence_reason}")
    lines.append(f"({answer.mode} pipeline, {answer.backend}, {answer.latency_s}s)")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(prog="infobridge")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("ask", "trail"):
        p = sub.add_parser(name)
        p.add_argument("sources", help="directory of source files")
        p.add_argument("question")
        p.add_argument("--backend", default=None, choices=["gemini", "extractive"])
        p.add_argument("--mode", default="full", choices=["baseline", "full"],
                       help="baseline = v0.1 naive RAG; full = Hack 1 pipeline (default)")
    e = sub.add_parser("eval")
    e.add_argument("--data", default="data/synthetic")
    e.add_argument("--backend", default="gemini", choices=["gemini", "extractive"])
    e.add_argument("--tag", default="hack1_v0.1")
    e.add_argument("--mode", default="full", choices=["baseline", "full"],
                   help="baseline = v0.1 naive RAG; full = Hack 1 pipeline (default)")
    e.add_argument("--cases", nargs="*", help="only these case ids (to spread free-tier quota over several runs)")
    c = sub.add_parser("compare", help="before/after table from two eval runs -> results/before_after.md")
    c.add_argument("--before", default="baseline_v0.1_rerun")
    c.add_argument("--after", default="hack1_v0.1")
    c.add_argument("--out", default="results/before_after.md")
    args = parser.parse_args()

    if args.cmd == "eval":
        result = run(args.data, args.backend, args.tag, mode=args.mode, only=args.cases)
        print(to_markdown(result["rows"], result["summary"], f"{args.tag} ({args.mode}, {args.backend})",
                          result["cases"]))
        print(f"Saved to results/{args.tag}.json and .md")
        return
    if args.cmd == "compare":
        load = lambda tag: json.loads(Path(f"results/{tag}.json").read_text())
        table = before_after(load(args.before), load(args.after))
        Path(args.out).write_text(table)
        print(table + f"\nSaved to {args.out}")
        return

    bridge = InfoBridge(backend=args.backend, mode=args.mode)
    bridge.ingest(args.sources)
    if bridge.extraction_failed:
        print(f"Note: LLM fact extraction failed for {', '.join(bridge.extraction_failed)}; their text facts are missing.")
    answer = bridge.ask(args.question)
    if args.cmd == "ask":
        print(render(answer))
    else:
        print(json.dumps(answer_trail(answer, bridge.documents, bridge.store), indent=2))


if __name__ == "__main__":
    main()
