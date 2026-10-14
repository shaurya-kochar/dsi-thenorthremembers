## hack1_v0.1_extractive (full, extractive)

### Per question

| Case | Q | Retr. recall | Fact recall | Cit. validity | Cit. accuracy | Cit. correct | Unsupported | Conflict (text) | Conflict (struct.) | Verdict | Latency (s) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| case_01_simple | q1 | 1.00 | 1.00 | 1.00 | 1.00 | 0.80 | 0.00 | – | – | – | 0.34 |
| case_02_medium | q1 | 1.00 | 0.50 | 1.00 | 1.00 | 1.00 | 0.00 | – | – | – | 0.28 |
| case_03_conflict | q1 | 1.00 | 0.29 | 1.00 | 1.00 | 1.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.25 |
| case_04_sunday_long_run | q1 | 1.00 | 0.50 | 1.00 | 1.00 | 1.00 | 0.00 | 0.00 | 0.00 | – | 0.26 |
| case_04_sunday_long_run | q2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 0.00 | 0.00 | – | 0.26 |
| case_04_sunday_long_run | q3 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 0.00 | 0.00 | – | 0.25 |
| case_04_sunday_long_run | q4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 0.00 | 0.00 | 0.27 |
| case_04_sunday_long_run | q5 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 0.00 | 0.00 | 0.26 |
| case_04_sunday_long_run | q6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 0.00 | – | 0.26 |
| case_04_sunday_long_run | q7 | – | – | 1.00 | – | – | 0.00 | – | – | 0.00 | 0.26 |
| case_05_volunteer_attendance | q1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 0.00 | 0.00 | – | 0.27 |
| case_05_volunteer_attendance | q2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 0.00 | 0.00 | 0.27 |
| case_05_volunteer_attendance | q3 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 0.00 | 0.00 | 0.26 |
| case_05_volunteer_attendance | q4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 0.00 | – | 0.26 |
| case_05_volunteer_attendance | q5 | 1.00 | 1.00 | 1.00 | 1.00 | 0.67 | 0.00 | 1.00 | 0.00 | – | 0.27 |
| case_05_volunteer_attendance | q6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 0.00 | 0.00 | – | 0.37 |
| case_06_event_schedule | q1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 0.00 | – | 0.35 |
| case_06_event_schedule | q2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 0.00 | – | 0.28 |
| case_06_event_schedule | q3 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 0.00 | – | 0.26 |
| case_06_event_schedule | q4 | 1.00 | 0.50 | 1.00 | 1.00 | 1.00 | 0.00 | – | – | – | 0.25 |
| case_07_race_day_logistics | q1 | 1.00 | 1.00 | 1.00 | 1.00 | 0.50 | 0.00 | 0.00 | 0.00 | – | 0.28 |
| case_07_race_day_logistics | q2 | 1.00 | 1.00 | 1.00 | 1.00 | 0.50 | 0.00 | 1.00 | 0.00 | – | 0.27 |
| case_07_race_day_logistics | q3 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 0.00 | 0.00 | – | 0.27 |

### Summary

| Split | Questions | Retr. recall | Fact recall | Cit. validity | Cit. accuracy | Cit. correct | Unsupported | Conflict (text) | Conflict (struct.) | Verdict | Latency (s) | ER F1 | Conflict precision | Conflicts caught |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| build | 16 | 1.00 | 0.89 | 1.00 | 1.00 | 0.96 | 0.00 | 0.54 | 0.00 | 0.00 | 0.28 | 0.99 | 1.00 | 0.10 |
| held_out | 7 | 1.00 | 0.93 | 1.00 | 1.00 | 0.86 | 0.00 | 0.67 | 0.00 | – | 0.28 | 1.00 | 1.00 | 0.12 |
| all | 23 | 1.00 | 0.90 | 1.00 | 1.00 | 0.93 | 0.00 | 0.58 | 0.00 | 0.00 | 0.28 | 0.99 | 1.00 | 0.11 |

### Per case

| Case | Split | ER F1 | Flagged | Planted | Caught | Precision | Missed conflicts |
|---|---|---|---|---|---|---|---|
| case_01_simple | build | 1.00 | 0 | 0 | 0 | – | – |
| case_02_medium | build | 0.96 | 0 | 0 | 0 | – | – |
| case_03_conflict | build | 1.00 | 0 | 2 | 0 | – | C1, C2 |
| case_04_sunday_long_run | build | 1.00 | 1 | 9 | 1 | 1.00 | C1, C2, C3, C4, C5, C6, C7, C8 |
| case_05_volunteer_attendance | build | 1.00 | 1 | 8 | 1 | 1.00 | C1, C2, C3, C4, C5, C6, C8 |
| case_06_event_schedule | held_out | 1.00 | 0 | 4 | 0 | – | C1, C2, C3, C4 |
| case_07_race_day_logistics | held_out | 1.00 | 1 | 4 | 1 | 1.00 | C1, C2, C3 |

### Failing questions

- case_02_medium q1: missed facts ['F4', 'F5', 'F6']
- case_03_conflict q1: missed facts ['F1', 'F2', 'F3', 'F4', 'F5']; verdict None
- case_04_sunday_long_run q1: missed facts ['F1']
- case_04_sunday_long_run q4: missed facts none; verdict None
- case_04_sunday_long_run q5: missed facts none; verdict None
- case_04_sunday_long_run q7: missed facts none; verdict None
- case_05_volunteer_attendance q2: missed facts none; verdict None
- case_05_volunteer_attendance q3: missed facts none; verdict None
- case_06_event_schedule q4: missed facts ['F4']
