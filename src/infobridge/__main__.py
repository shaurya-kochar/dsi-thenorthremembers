"""Command line entry point.

    python -m infobridge ask  data/synthetic/case_03_conflict/sources "Is Ravi Sharma eligible for HMTP 2026B?"
    python -m infobridge eval --backend gemini --tag baseline_v0.1
    python -m infobridge trail data/synthetic/case_03_conflict/sources "Is Ravi Sharma eligible ...?"
    python -m infobridge ask --mode baseline ...   # the v0.1 naive-RAG path, for the before/after comparison
"""

from __future__ import annotations

import argparse
import json

from .evaluation import run, to_markdown
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
    e.add_argument("--tag", default="baseline_v0.1")
    args = parser.parse_args()

    if args.cmd == "eval":
        result = run(args.data, args.backend, args.tag)
        print(to_markdown(result["rows"], result["summary"], f"{args.tag} ({args.backend})"))
        print(f"Saved to results/{args.tag}.json and .md")
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
