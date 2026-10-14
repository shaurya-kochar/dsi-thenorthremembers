## Before / after: baseline_v0.1_rerun_extractive → hack1_v0.1_extractive

Baseline = Sprint 2 naive RAG (`--mode baseline`); full = Hack 1 pipeline (`--mode full`). Backend: extractive. Build questions: 16, held-out questions: 7. Case 3 rows are on the build set. The baseline has no resolver or detector, so its ER F1 and conflict precision are '–' and its conflicts caught are 0.

| Metric | Build: baseline | Build: full | Held-out: baseline | Held-out: full | Target |
|---|---|---|---|---|---|
| Retrieval recall (case 3) | 0.57 | 1.00 |  |  | ≥ 0.90 |
| Retrieval recall | 0.95 | 1.00 | 1.00 | 1.00 |  |
| Fact recall | 0.88 | 0.89 | 0.93 | 0.93 |  |
| Structured conflict recall (per question) | 0.00 | 0.00 | 0.00 | 0.00 | ≥ 0.90 |
| Conflicts caught (all planted) | 0.00 | 0.10 | 0.00 | 0.12 | ≥ 0.90 build, ≥ 0.80 held-out |
| Conflict precision | – | 1.00 | – | 1.00 | ≥ 0.80 |
| Conflicts stated in the answer text | 0.61 | 0.54 | 0.67 | 0.67 |  |
| Entity resolution F1 | – | 0.99 | – | 1.00 | ≥ 0.85 |
| Citation validity | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| Citation correctness (file, row, field) | 0.89 | 0.96 | 0.82 | 0.86 | ≥ 0.90 held-out |
| Citation accuracy | 0.98 | 1.00 | 1.00 | 1.00 |  |
| Unsupported claims | 0.00 | 0.00 | 0.00 | 0.00 | lower is better |
| Verdict accuracy (case 3) | 0.00 | 0.00 |  |  | 1.00 |
| Verdict accuracy | 0.00 | 0.00 | – | – |  |
| Latency (s) | 0.13 | 0.28 | 0.13 | 0.28 |  |

### Why this table uses the extractive backend

The table above is the reproducible offline run (`--backend extractive`: retrieval only, no LLM), so
the verdict rows are 0 by construction and conflicts that live only in chat / PDF text (most of
them) cannot be detected without Gemini fact extraction. The Gemini runs of both modes
(`baseline_v0.1_rerun`, `hack1_v0.1`) need about 55 requests; the free tier allows 20 requests per
day per key for gemini-3.8-flash, and the team's keys hit `429 RESOURCE_EXHAUSTED` during the hack.
They are to be re-run with:

```bash
python -m infobridge eval --backend gemini --mode baseline --tag baseline_v0.1_rerun
python -m infobridge eval --backend gemini --mode full --tag hack1_v0.1
python -m infobridge compare --before baseline_v0.1_rerun --after hack1_v0.1
```

### With Gemini (gemini-3.8-flash), measured today

Conflict detector with Gemini text extraction on the two demo cases
(`results/gemini_extraction_cases_03_04.json`):

| Case | ER F1 | Flagged | Planted | Caught | Precision |
|---|---|---|---|---|---|
| case_03_conflict | 1.00 | 2 | 2 | 2 | 1.00 |
| case_04_sunday_long_run | 1.00 | 11 | 9 | 9 | 0.82 |
| **pooled** | 1.00 | 13 | 11 | 11 | 0.85 |

The two extra flags in case 04 are formatting only ("km 6" vs "km 6 water station" for Bhargavi
Kulkarni's and Sai Kiran's station): free-text station names are not normalised yet.

The two demo questions, full pipeline:

| Question | Sprint 2 baseline (Gemini) | Hack 1 full pipeline (Gemini) |
|---|---|---|
| Is Ravi Sharma eligible for HMTP Batch 2026B? | UNCERTAIN; misses his membership and registration rows; no conflicts | **YES**; every rule cited (Rules 1–4), members.csv row 5 and registrations.csv row 3 cited; C1 and C2 flagged with both sources, "neither conflict affects his eligibility"; no Ravi Shankar; confidence medium |
| How many volunteers confirmed for the Sunday long run, and who is the lead? | – (new question) | Lead **Vikram Rao**; 14 (plan PDF, para 5) vs 12 (chat, msg 5) both cited and flagged; confidence medium: "Two sources disagree on the volunteer count of Sunday Long Run (14 vs 12), and 5 more conflicts are open." |
