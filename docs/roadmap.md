# InfoBridge: Sprint & Hack Roadmap

**Team:** The North Remembers · **Project:** DSI 9A (Hyderabad Runners)  
**Covers:** Sprint 2 (27 Sep) → Showcase (20 Nov 2026)

---

## Overview

We build InfoBridge in small steps. Each step adds one capability and is measured on the same synthetic test cases, so we can show improvement at every checkpoint.

| Phase | Dates | Version | Focus | Key output |
|---|---|---|---|---|
| **Sprint 2** | 27 Sep – 10 Oct | v0.1 foundations | Basic architecture and a working baseline | Technical Design Doc, baseline results |
| **Hack 1** | 10 Oct | v0.1 | Connect names across sources; flag conflicts | Demo video, revised doc |
| **Sprint 3** | 11 – 24 Oct | v0.2 | Smarter extraction, knowledge graph, more test cases | All components in place, test results |
| **Sprint 4** | 25 Oct – 7 Nov | v0.9 | Testing, edge cases, robustness, open data | Evaluation and failure analysis |
| **Hack 2** | 7 Nov | v1.0 | Polish and final evaluation | Final Technical Design Doc |
| **Sprint 5** | 8 – 14 Nov | v1.0 final | Package and defend | Slides, poster, video, final repo |

---

## Sprint 2: Basic architecture & implementation

**Goal:** a first working version that answers a question from several sources with citations, plus a baseline score to improve on.

### Architecture (v0.1)

```
 Source files:  CSV · Excel · PDF · WhatsApp export · Email
        │
        ▼
 [1] Ingestion        split each file into small chunks (row / message /
        │             paragraph), each tagged with its exact location
        ▼
 [2] Vector store     embed the chunks; find the ones most relevant to the
        │             question  (ChromaDB + all-MiniLM-L6-v2)
        ▼
 [3] Synthesis        LLM answers using only the retrieved chunks; every
        │             claim must cite a source  (Gemini)
        ▼
 [4] Citation check   flag claims with missing or invalid citations
        │
        ▼
 Answer:  verdict + cited claims + sources list
          (or "not enough evidence" + where to look)
```

Later sprints add these blocks between ingestion and synthesis: **fact extraction → entity resolution → conflict detection → knowledge graph.**

### What we build in Sprint 2

| Part | Tech | What it does |
|---|---|---|
| Ingestion | pandas, PyMuPDF | Reads CSV, Excel, PDF, WhatsApp exports and emails; splits them into chunks with an exact location (e.g. `members.csv` row 5) |
| Vector store | ChromaDB + all-MiniLM-L6-v2 | Finds the chunks most relevant to the question |
| Synthesis | Gemini (free tier) | Writes the answer using only the retrieved chunks; every claim must cite a source |
| Citation check | Python | Flags claims that cite nothing, or cite a source that wasn't retrieved |
| Fallback | Python | If nothing relevant is found, says so and points to the closest sources instead of guessing |
| Synthetic data | Hand-written | 3 test cases (simple / medium / conflict), each with an answer key |
| Evaluation | Python script | Scores answers against the answer key |

**Not in Sprint 2:** entity resolution, conflict detection, knowledge graph. The baseline is supposed to fail where these are needed, which shows why we need them.

### Test cases

| Case | Sources | Question | What makes it hard |
|---|---|---|---|
| 1 – Simple | Events sheet, email | Details of the 25 Oct long run | Nothing. This is the control case |
| 2 – Medium | Volunteer roster, WhatsApp, first-aid PDF | Who's at Aid Station 3, and are they trained? | Same people with different names (*Srini* = *Srinivas Rao Kumar*); a look-alike (*Srinivas Reddy*) |
| 3 – Conflict | Members sheet, registrations, WhatsApp, rules PDF | Is Ravi Sharma eligible for the training programme? | *Ravi Sharma / R. Sharma / Ravi S.*; look-alike *Ravi Shankar*; 2 contradictions between sources |

### Evaluation criteria

| Metric | Question it answers |
|---|---|
| Retrieval recall | Did we find the chunks that hold the answer? |
| Fact recall | Did the answer include all the key facts? |
| Citation validity | Does every citation point to a real source chunk? |
| Conflict recall | Did we flag the planted contradictions? |
| Verdict accuracy | Was the YES/NO correct? |
| Latency | How long did it take? |

### Baseline result (retrieval only)

| Case | Retrieval recall | Fact recall | Citation validity | Conflict recall |
|---|---|---|---|---|
| 1 – Simple | 1.00 | 1.00 | 1.00 | – |
| 2 – Medium | 0.67 | 0.50 | 1.00 | – |
| 3 – Conflict | 0.57 | 0.14 | 1.00 | 0.00 |

- **Worked:** every citation points to an exact location; the simple case is answered completely.
- **Didn't work:** when names differ across sources, the right chunks aren't found. Ravi Sharma's own membership row ranks 20th of 29, below the look-alike Ravi Shankar. Conflicts are never flagged.
- **To do:** add the Gemini baseline numbers once an API key is set up.

### Sprint 2 deliverables

- ☑ Basic pipeline running end to end (code on GitHub)
- ☑ 3 synthetic test cases with answer keys
- ☑ Baseline results: what worked and what didn't
- ☐ Gemini baseline run
- ☐ Technical Design Doc submitted (Moodle)

---

## Hack 1 (10 Oct): Make it work, find what breaks

**Goal:** fix the two biggest baseline failures and demo it live.

1. **Simple entity resolution:** treat records as the same person if the phone or email matches, or if the names are compatible (*R. Sharma* ~ *Ravi Sharma*, *Srini* ~ *Srinivas*). Never merge different surnames (*Sharma* ≠ *Shankar*).
2. **Simple conflict detection:** compare values for the same person across sources (dates, statuses) and flag any differences, using spreadsheet columns plus dates found in text.
3. **Show conflicts in the answer:** list each conflict with both values and their sources.
4. **Re-run the evaluation** and compare with the baseline.

**Deliverables:** revised Technical Design Doc, demo video (question → answer → evidence → conflict), PoC v0.1 on GitHub, list of issues and questions for instructors.

---

## Sprint 3 (11 – 24 Oct): Build it out → v0.2

**Goal:** all 7 components in place, clearly better than Hack 1.

- Act on Hack 1 feedback; fix the worst failures first.
- **LLM fact extraction** from chats, PDFs and emails (not just spreadsheet columns).
- **Knowledge graph** (NetworkX): people, events and their facts, each linked to its source.
- **Better retrieval:** fetch every chunk about the person asked about, not just the most similar text.
- **Full evidence trail:** source → extracted fact → matched entity → claim.
- **More test cases:** 5–6 in total, including one written by a teammate who didn't build the matcher.

**Deliverables:** PoC v0.2 on GitHub, test spec and results, known limitations.

---

## Sprint 4 (25 Oct – 7 Nov): Validate & harden → v0.9

**Goal:** credible, tested, stable.

- **Systematic testing:** unit tests per component plus end-to-end tests on all cases.
- **Edge cases:** empty files, questions with no answer in the sources, heavily conflicting sources, near-identical names.
- **Robustness:** handle LLM errors and rate limits; cache results; fail with a clear message rather than silently.
- **One real open-data scenario** (OGD India / WHO / OpenAlex) to show the approach works beyond our own test data.
- **Better scoring:** a manual or LLM-based check of answer quality, in addition to keyword matching.

**Deliverables:** revised Technical Design Doc (evaluation, failure analysis, limitations), PoC v0.9, demo plan for Hack 2.

---

## Hack 2 (7 Nov): Complete & polish → v1.0

- Fix the remaining high-priority issues.
- Make outputs clean and consistent; make the demo run reliably.
- Final evaluation run; a results table comparing every version (v0.1 → v1.0).
- Prepare a backup recording in case the live demo fails.

**Deliverables:** final Technical Design Doc, PoC v1.0 on GitHub.

---

## Sprint 5 (8 – 14 Nov): Package & defend

- Clean the code; write the README (setup, how to run, architecture).
- Final versions of the Functional Scope Doc, Design Doc and Technical Design Doc.
- **Slides, poster and demo video:** problem → solution → technology → results.
- Review with NGOs (table discussions).
- Prepare for likely questions:
    - "How is this different from ChatGPT?"
    - "Would it work on real NGO data?"
    - "What would production need?"
    - "Which other NGOs could use it?"

**Then:** Demo 2 (14 Nov) · Final assessment (18 Nov) · Showcase (20 Nov).

---

## How the metrics should improve

| Metric | v0.1 baseline | Hack 1 | v0.2 | v1.0 |
|---|---|---|---|---|
| Retrieval recall (case 3) | 0.57 | – | ≥ 0.90 | ≥ 0.90 |
| Conflict recall | 0.00 | ≥ 0.50 | ≥ 0.90 | ≥ 0.90 |
| Entity resolution F1 | – | measured | ≥ 0.85 | ≥ 0.90 |
| Citation validity | 1.00 | 1.00 | 1.00 | 1.00 |
| Verdict accuracy | TBD | – | 1.00 | 1.00 |

These are targets on our synthetic cases only. They don't show that the system would work on real NGO data; understanding that gap is part of the project.
