# InfoBridge — PoC v0.1

Evidence-preserving multi-source information synthesis for NGO coordinators
(DSI 2026, Project 9A, anchor NGO: Hyderabad Runners, team The North Remembers).

Ask a plain-language question over a folder of messy sources (spreadsheets, PDFs,
WhatsApp exports, emails). You get a cited answer where every claim points to an
exact row, message or paragraph.

**Status (Sprint 2):** ingestion → vector retrieval → naive-RAG synthesis with
validated citations → evaluation against a synthetic gold standard. Entity
resolution, conflict detection and the knowledge graph have fixed interfaces and
are built in Hack 1. See [docs/technical_design_doc.md](docs/technical_design_doc.md).

## Setup

```bash
uv venv --python 3.10 .venv && uv pip install --python .venv/bin/python -e ".[dev]"
# or: python -m venv .venv && .venv/bin/pip install -e ".[dev]"
cp .env.example .env        # add GEMINI_API_KEY (not needed for --backend extractive)
```

## Run

```bash
source .venv/bin/activate

# Ask a question (gemini = LLM synthesis, extractive = retrieval only, no key needed)
python -m infobridge ask data/synthetic/case_03_conflict/sources \
  "Is Ravi Sharma eligible for the Half Marathon Training Programme Batch 2026B?"

# Full evidence trail (source → chunk → retrieval → claim) as JSON
python -m infobridge trail data/synthetic/case_03_conflict/sources "Is Ravi Sharma eligible ...?"

# Evaluate against all synthetic cases; writes results/<tag>.json and .md
python -m infobridge eval --backend gemini --tag baseline_v0.1

pytest                      # unit + gold-integrity tests
python scripts/build_synthetic.py   # re-render PDFs/Excel after editing pdf_src/ or xlsx_src/
python scripts/md_to_pdf.py docs/technical_design_doc.md   # rebuild a doc's PDF (needs Chrome)
```

## Layout

```
src/infobridge/
  models.py        data contracts shared by all components (the "APIs")
  ingestion.py     [1] CSV / Excel / PDF / WhatsApp / email → citable chunks
  extraction.py    [2] facts from chunks                      (Hack 1 stub)
  resolution.py    [3] entity resolution                      (Hack 1 stub)
  graph.py         [4] knowledge graph with provenance edges  (Hack 1 stub)
  conflicts.py     [5] conflict detector                      (Hack 1 stub)
  retrieval.py     vector store (ChromaDB + all-MiniLM-L6-v2)
  synthesis.py     [6] RAG synthesis, citation validation, fallback
  provenance.py    [7] evidence trail per claim
  pipeline.py      wires the components together
  evaluation.py    metrics against gold.json
data/synthetic/case_*/
  sources/         what the pipeline ingests
  gold.json        planted facts, entity mentions, conflicts, expected verdicts
  pdf_src/ xlsx_src/  editable text originals of the binary sources
results/           evaluation outputs
docs/              design docs (.md source + .pdf)
scripts/           build_synthetic.py, md_to_pdf.py, finalize_baseline.py
```

## Sprint 2 deliverables

| Deliverable | Where | Status |
|---|---|---|
| Technical Design Doc: architecture, initial implementation, baseline result | [docs/technical_design_doc.pdf](docs/technical_design_doc.pdf) (Moodle) | Done, except the Gemini row in §6.2 |
| PoC v0.1 foundations | this repo (GitHub) | Done |
| Sprint-by-sprint plan | [docs/roadmap.pdf](docs/roadmap.pdf) | Done |
| Hack 1 playbook (tasks, owners, timeline, demo script) | [docs/sprint2_status_and_hack1_plan.pdf](docs/sprint2_status_and_hack1_plan.pdf) | Done |

To finish the Gemini baseline (needs `GEMINI_API_KEY` in `.env`):

```bash
python scripts/finalize_baseline.py   # runs the eval, fills §6.2 of the doc, rebuilds the PDF
```
