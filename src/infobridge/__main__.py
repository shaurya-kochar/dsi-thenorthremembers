"""Command line entry point.

    python -m infobridge ask  data/synthetic/case_03_conflict/sources "Is Ravi Sharma eligible for HMTP 2026B?"
    python -m infobridge eval --backend gemini --tag baseline_v0.1
    python -m infobridge trail data/synthetic/case_03_conflict/sources "Is Ravi Sharma eligible ...?"
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
    lines.append(f"Conflicts flagged: {len(answer.conflicts)}   ({answer.backend}, {answer.latency_s}s)")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(prog="infobridge")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("ask", "trail"):
        p = sub.add_parser(name)
        p.add_argument("sources", help="directory of source files")
        p.add_argument("question")
        p.add_argument("--backend", default=None, choices=["gemini", "extractive"])
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

    bridge = InfoBridge(backend=args.backend)
    bridge.ingest(args.sources)
    answer = bridge.ask(args.question)
    if args.cmd == "ask":
        print(render(answer))
    else:
        print(json.dumps(answer_trail(answer, bridge.documents), indent=2))


if __name__ == "__main__":
    main()
