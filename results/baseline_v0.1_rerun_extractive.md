## baseline_v0.1_rerun_extractive (baseline, extractive)

### Per question

| Case | Q | Retr. recall | Fact recall | Cit. validity | Cit. accuracy | Cit. correct | Unsupported | Conflict (text) | Conflict (struct.) | Verdict | Latency (s) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| case_01_simple | q1 | 1.00 | 1.00 | 1.00 | 1.00 | 0.80 | 0.00 | – | – | – | 0.14 |
| case_02_medium | q1 | 0.67 | 0.50 | 1.00 | 0.67 | 0.67 | 0.00 | – | – | – | 0.14 |
| case_03_conflict | q1 | 0.57 | 0.14 | 1.00 | 1.00 | 1.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.13 |
| case_04_sunday_long_run | q1 | 1.00 | 0.50 | 1.00 | 1.00 | 1.00 | 0.00 | 0.00 | 0.00 | – | 0.14 |
| case_04_sunday_long_run | q2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 0.00 | – | 0.13 |
| case_04_sunday_long_run | q3 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 0.00 | – | 0.13 |
| case_04_sunday_long_run | q4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 0.00 | 0.00 | 0.13 |
| case_04_sunday_long_run | q5 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.13 |
| case_04_sunday_long_run | q6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 0.00 | – | 0.13 |
| case_04_sunday_long_run | q7 | – | – | 1.00 | – | – | 0.00 | – | – | 0.00 | 0.13 |
| case_05_volunteer_attendance | q1 | 1.00 | 1.00 | 1.00 | 1.00 | 0.50 | 0.00 | 0.00 | 0.00 | – | 0.14 |
| case_05_volunteer_attendance | q2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 0.00 | 0.00 | 0.13 |
| case_05_volunteer_attendance | q3 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 0.00 | 0.00 | 0.12 |
| case_05_volunteer_attendance | q4 | 1.00 | 1.00 | 1.00 | 1.00 | 0.67 | 0.00 | 1.00 | 0.00 | – | 0.12 |
| case_05_volunteer_attendance | q5 | 1.00 | 1.00 | 1.00 | 1.00 | 0.67 | 0.00 | 1.00 | 0.00 | – | 0.13 |
| case_05_volunteer_attendance | q6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 0.00 | 0.00 | – | 0.12 |
| case_06_event_schedule | q1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 0.00 | – | 0.13 |
| case_06_event_schedule | q2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 0.00 | – | 0.12 |
| case_06_event_schedule | q3 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 0.00 | – | 0.12 |
| case_06_event_schedule | q4 | 1.00 | 0.50 | 1.00 | 1.00 | 1.00 | 0.00 | – | – | – | 0.13 |
| case_07_race_day_logistics | q1 | 1.00 | 1.00 | 1.00 | 1.00 | 0.50 | 0.00 | 0.00 | 0.00 | – | 0.14 |
| case_07_race_day_logistics | q2 | 1.00 | 1.00 | 1.00 | 1.00 | 0.25 | 0.00 | 1.00 | 0.00 | – | 0.13 |
| case_07_race_day_logistics | q3 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 0.00 | 0.00 | – | 0.13 |

### Summary

| Split | Questions | Retr. recall | Fact recall | Cit. validity | Cit. accuracy | Cit. correct | Unsupported | Conflict (text) | Conflict (struct.) | Verdict | Latency (s) | ER F1 | Conflict precision | Conflicts caught |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| build | 16 | 0.95 | 0.88 | 1.00 | 0.98 | 0.89 | 0.00 | 0.61 | 0.00 | 0.00 | 0.13 | – | – | – |
| held_out | 7 | 1.00 | 0.93 | 1.00 | 1.00 | 0.82 | 0.00 | 0.67 | 0.00 | – | 0.13 | – | – | – |
| all | 23 | 0.96 | 0.89 | 1.00 | 0.98 | 0.87 | 0.00 | 0.63 | 0.00 | 0.00 | 0.13 | – | – | – |

### Failing questions

- case_02_medium q1: missed facts ['F3', 'F4', 'F5']
- case_03_conflict q1: missed facts ['F1', 'F2', 'F3', 'F4', 'F5', 'F7']; verdict None
- case_04_sunday_long_run q1: missed facts ['F1']
- case_04_sunday_long_run q4: missed facts none; verdict None
- case_04_sunday_long_run q5: missed facts none; verdict None
- case_04_sunday_long_run q7: missed facts none; verdict None
- case_05_volunteer_attendance q2: missed facts none; verdict None
- case_05_volunteer_attendance q3: missed facts none; verdict None
- case_06_event_schedule q4: missed facts ['F4']
