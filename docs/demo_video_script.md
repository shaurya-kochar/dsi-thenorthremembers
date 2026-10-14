# Hack 1 demo video: script (about 3.5 minutes, two takes)

Task E4. The video shows both test questions in the app: first the before/after story on the
Ravi Sharma case, then the coordinator flow on the Sunday long run. Record the browser window
only (1920×1080, browser zoom 110%), with the narration recorded live.

## Setup (before the first take)

```bash
# 1. the API, with Gemini text extraction (needed for the conflicts that live in chats and PDFs)
INFOBRIDGE_API_LLM_EXTRACTION=1 .venv/bin/uvicorn infobridge.api:app --port 8000
# 2. the app, in a second terminal
.venv/bin/streamlit run app.py
```

- Warm the cache: ask both demo questions once (Full pipeline, gemini) before recording, so
  the answers come from `results/cache/` and take seconds instead of minutes.
- Open `results/before_after.md` in a second browser tab (rendered on GitHub) for step 8.
- Sidebar should say "Pipeline runs API at http://127.0.0.1:8000". If the API is down the app
  still works in-process; nothing in the script changes.
- Between takes, restart the API so Conflict Review shows every conflict as open again.

## Script

| # | Time | Screen and clicks | Narration (key points) |
|---|---|---|---|
| 1 | 0:00–0:20 | **Home**, case `case_03_conflict`. Scroll the Sources table: members.csv, registrations.csv, whatsapp_coach_group.txt, programme_rules.pdf. | A coordinator asks whether Ravi Sharma can join the half-marathon batch. The answer is spread over four files. Ravi appears as "Ravi Sharma", "R. Sharma" and "Ravi S."; there is a look-alike, Ravi Shankar; and two sources contradict each other. |
| 2 | 0:20–0:50 | Pipeline = **Baseline (v0.1)**, engine = gemini, **Ask**. On Query Result point at the verdict, the claims and "Conflicts 0". | This is our Sprint 2 baseline: plain vector search plus an LLM. It misses his membership and registration rows, says nothing about the conflicts, and cannot give a verdict. |
| 3 | 0:50–1:35 | Sidebar **Home**, Pipeline = **Full pipeline**, **Ask**. Show the YES banner, the confidence note, the claims with their [S#] badges, and the two conflict cards (medical clearance date, batch start date) with both sources and suggestions. | The full pipeline resolves the three names to one person, keeps Ravi Shankar out, retrieves every rule, and answers YES with a citation for each rule. The two conflicts are flagged with both sources, and the answer says neither changes the verdict. Confidence is medium because those conflicts are open. |
| 4 | 1:35–1:50 | **Home**, case `case_04_sunday_long_run`. Show the Sources table: volunteer_signups.xlsx, sunday_long_run_plan.pdf, whatsapp_run_coordinators.txt, public_who_heat_and_health_excerpt.pdf. | Now the coordinator's own question, over a volunteer sheet, the event plan PDF, the coordinators' WhatsApp export and a slice of public WHO data. |
| 5 | 1:50–2:20 | Question is prefilled: *How many volunteers confirmed for the Sunday long run, and who is the lead?* Full pipeline, **Ask**. Point at the answer, the confidence note ("Two sources disagree on the volunteer count … (14 vs 12)") and the volunteer-count card. | The lead is Vikram Rao. The plan PDF says 14 confirmed, the chat says 12 after two drop-outs, so the answer gives both, cites both, and the confidence note says why it is only medium. |
| 6 | 2:20–2:40 | Click a citation badge, e.g. **[S#] whatsapp_run_coordinators.txt · msg=5**. On **Evidence Trail** walk down: ① source → ② chunk (message 5, dated 11 Nov) → ③ extracted fact `volunteer_count = 12` → ④ "Sunday Long Run" → `event:sunday-long-run` with match evidence → ⑥ claim. | Every value traces back to its exact file, row or message, and field, and to the entity it was resolved to. |
| 7 | 2:40–3:00 | Sidebar **Conflict Review** (toggle "Only conflicts in the last answer" on). On the volunteer-count conflict show 14 (plan PDF, para 5) and 12 (chat, msg 5) side by side, read the suggestion, click **Accept this value** under 12. Show the ✅ accepted state. | Both values side by side with their sources and a suggestion; the coordinator accepts the newer count, and the decision is stored. |
| 8 | 3:00–3:20 | Second tab: `results/before_after.md`. | The before/after table on the build and held-out sets: retrieval recall on case 3 from 0.57 to 1.00, conflicts caught and conflict precision, entity-resolution F1, citation correctness, and the verdict on case 3. Held-out cases 06 and 07 were never used for tuning. |
| 9 | 3:20–3:35 | Back to the app, Home. | What does not work yet (from the feedback log): text facts depend on Gemini, whose free tier was overloaded during the hack; "the flyover site" cannot be linked to Aid Station 3 by rules; scoring is keyword-based. Our questions for the instructors are in the design doc. |

## Checklist per take

- [ ] Baseline answer shows no conflicts; full answer shows C1 and C2 for case 3
- [ ] No "Ravi Shankar" anywhere in the full answer
- [ ] Case 4 answer names Vikram Rao and both counts, confidence medium
- [ ] Citation badge opens the trail with file, row/message and field
- [ ] Accept shows the ✅ state
- [ ] Before/after table visible for at least 5 seconds
