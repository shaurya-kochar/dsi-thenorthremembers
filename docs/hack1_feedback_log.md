# Hack 1 Feedback Log

Filled in during the hack (14 October 2026). It drives the Sprint 3 backlog.

## What broke

| Time | Component | What happened | Root cause (if known) | Fixed? |
|---|---|---|---|---|
| Turn 1 | Data (#1) | OGD India tables could not be fetched | data.gov.in sample key is rate-limited; needs a personal key | No: WHO and OpenAlex slices only |
| Turn 2 | Git | Shoaib could not push #4 / #5 | His GitHub account had no access to the RCTS repo | Yes: pushed once access was granted |
| Turns 2–4 | LLM extraction | `503 UNAVAILABLE` ("high demand") on many calls; documents were skipped | Free-tier model overloaded | Partly: retries with backoff, failed documents reported in `extraction_failed`, cache makes re-runs cheap |
| Turns 3–4 | LLM | `429 RESOURCE_EXHAUSTED` on Shaurya's key, later on Prashant's | Free tier allows 20 requests per day per key for gemini-3.8-flash | No: each person uses their own key; the Gemini evaluation could not run in one day |
| Turn 4 | LLM | One synthesis call hung for over 15 minutes | No request timeout on the Gemini client | Yes: 5-minute timeout, then retry (PR #20) |
| Turn 3 | Knowledge graph (#4) | The same value stated in four registration rows became one edge | Fact edges were keyed by attribute name | Yes: edges keyed by fact (#6) |
| Turn 4 | Retrieval (#5) | Ravi Sharma question answered UNCERTAIN with Gemini: "only Rule 3 is provided" | Rules 1, 2, 4 of the rules PDF never name the batch, so the entity channel missed them; other people's rows filled the evidence | Yes: every paragraph of a document about an asked programme/event is retrieved (PR #20); answer is now YES |
| Turn 4 | Data generator | Re-running `build_hack1_data.py` erased the new test questions | It deletes the case folder before writing the answer key | Yes: questions and facts are read before and kept |

## What took longer than expected

| Task | Planned | Actual | Why |
|---|---|---|---|
| LLM fact extraction (any case) | Seconds per document | 20–225 s per call, many retries | Free-tier latency and 503s |
| Gemini evaluation (#10) | One run per mode | Not possible in one day | ~55 requests needed, 20 per key per day |
| Conflict detector rules (#6) | Group and compare | Also categorical normalisation, name spellings, recency | LLM values come as written ("take me off the list"); PDFs and sheet rows carry the date they talk about, not when they were written |
| Confidence / suggestion wording | Small | Medium | Had to pick, per conflict, which side to cite (Ravi's own row, not another registrant's) |

## Assumptions that turned out wrong

- *An LLM returns the canonical option for categorical fields.* It returns the words of the message; signup status, attendance, payment and membership now go through a keyword normaliser (P0 of #6).
- *A chunk's date says how recent it is.* Only chat messages and e-mails carry the date they were written; a PDF plan is tagged with the event date and a sheet row with its date column.
- *Retrieving every chunk that names the asked entity is enough.* Rules documents rarely repeat the name in every rule.
- *Free-tier Gemini is enough for a full evaluation.* 20 requests per day per key is not.
- *"The flyover site" (case 02) can be linked to Aid Station 3 by rules.* It cannot without world knowledge.
- *Free-text values like station names compare equal after whitespace normalisation.* "km 6" vs "km 6 water station" is flagged as a conflict (2 false flags in case 04).

## Metrics: before vs after

Full tables: `results/before_after.md` (offline, extractive backend, all 23 questions, build and held-out),
`results/hack1_v0.1_extractive.md`, `results/baseline_v0.1_rerun_extractive.md`, and
`results/gemini_extraction_cases_03_04.json`. Summary:

| Metric | Sprint 2 baseline | Hack 1 | Target |
|---|---|---|---|
| Retrieval recall (case 3) | 0.57 | 1.00 | ≥ 0.90 |
| Retrieval recall (build / held-out) | 0.95 / 1.00 | 1.00 / 1.00 | |
| Entity resolution F1 (build / held-out) | – | 0.99 / 1.00 | ≥ 0.85 |
| Conflicts caught, cases 03 + 04 with Gemini extraction | 0 | 11 / 11 (1.00) | ≥ 0.90 |
| Conflict precision, cases 03 + 04 with Gemini extraction | – | 0.85 | ≥ 0.80 |
| Conflicts caught, all cases, no LLM (build / held-out) | 0.00 / 0.00 | 0.10 / 0.12 | text facts need Gemini |
| Conflict precision, no LLM | – | 1.00 | ≥ 0.80 |
| Citation validity | 1.00 | 1.00 | 1.00 |
| Citation correctness (build / held-out, extractive) | 0.89 / 0.82 | 0.96 / 0.86 | ≥ 0.90 held-out |
| Verdict, case 3 (Gemini) | UNCERTAIN | YES | YES |

Not yet measured: the Gemini runs of both modes on all 23 questions (`baseline_v0.1_rerun`, `hack1_v0.1`),
blocked by quota. Held-out conflict recall with Gemini extraction is therefore also still open.

## Questions for instructors

1. Is a pooled free-tier key, or a small paid quota, acceptable for the Sprint 3 evaluation, given that one full Gemini run needs ~55 requests and the free tier allows 20 per day?
2. Keyword-based fact scoring misses paraphrases. Is an LLM judge on a sample, checked by hand, an acceptable way to report fact recall?
3. Our held-out set is two cases (7 questions). Is that enough for the "held-out" claim, or should Sprint 3 add a third held-out case?
4. Should conflict severity depend on the question (whether the conflict changes a rule outcome) rather than a fixed rule per field?

## Sprint 3 backlog (from today)

| Priority | Item | Owner |
|---|---|---|
| Critical | Run the Gemini evaluation of both modes on all 23 questions (case by case with `--cases`, several keys or days) and update `results/before_after.md` | Prashant |
| Critical | Held-out conflict recall with Gemini extraction (cases 06, 07) | Prashant |
| Important | Normalise free-text values (station names, "km 6" vs "km 6 water station") before comparing; fixes the 2 false flags in case 04 | Pariza |
| Important | Question-aware severity: high when a conflict changes a rule outcome | Pariza |
| Important | Fetch the OGD India tables with a personal data.gov.in key; one real open-data scenario | Shaurya |
| Important | LLM-judge fact scoring on a sample, checked by hand | Prashant |
| Nice to have | Link descriptive place names ("the flyover site") to stations with a gazetteer or the LLM | Shoaib |
| Nice to have | Persist accepted conflict values across API restarts (SQLite file instead of memory) | Shoaib |
