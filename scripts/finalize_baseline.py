"""Finish the Sprint 2 baseline in one step (needs GEMINI_API_KEY in .env):

  1. runs the Gemini naive-RAG evaluation   -> results/baseline_v0.1.{json,md}
  2. inserts the results table into §6.2 of docs/technical_design_doc.md
  3. rebuilds docs/technical_design_doc.pdf

    python scripts/finalize_baseline.py
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from infobridge.config import settings  # noqa: E402
from infobridge.evaluation import run, to_markdown  # noqa: E402
from md_to_pdf import md_to_pdf  # noqa: E402

DOC = ROOT / "docs" / "technical_design_doc.md"
TAG = "baseline_v0.1"
MARKERS = re.compile(r"(<!-- GEMINI_BASELINE_START -->\n).*?(\n<!-- GEMINI_BASELINE_END -->)", re.DOTALL)


def main() -> None:
    if not settings.gemini_api_key:
        sys.exit("GEMINI_API_KEY is not set: copy .env.example to .env and add your key.")

    print(f"Running evaluation with {settings.model} ...")
    result = run(ROOT / "data" / "synthetic", "gemini", TAG, ROOT / "results")
    table = to_markdown(result["rows"], result["summary"], TAG).split("\n", 2)[2].strip()  # drop "## title"

    section = (f"Model: `{settings.model}`, top-k = {settings.top_k}. "
               f"Full answers: `results/{TAG}.json`.\n\n{table}")
    DOC.write_text(MARKERS.sub(lambda m: m.group(1) + section + m.group(2), DOC.read_text()))
    print(f"Updated §6.2 in {DOC.relative_to(ROOT)}")
    print("Wrote", md_to_pdf(DOC).relative_to(ROOT))
    print("\nNext: read the Gemini answers for case 3 in the JSON and add 2-3 lines to §7 "
          "(did it say YES? mention the conflicts? confuse Ravi Shankar?), then rebuild with\n"
          "  python scripts/md_to_pdf.py docs/technical_design_doc.md")


if __name__ == "__main__":
    main()
