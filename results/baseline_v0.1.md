## baseline_v0.1 (gemini)

| Case | Retr. recall | Fact recall | Cit. validity | Cit. accuracy | Unsupported | Conflict (text) | Conflict (struct.) | Verdict | Latency (s) |
|---|---|---|---|---|---|---|---|---|---|
| case_01_simple | 1.00 | 0.86 | 1.00 | 1.00 | 0.00 | – | – | – | 84.14 |
| case_02_medium | 0.67 | 1.00 | 1.00 | 0.67 | 0.00 | – | – | – | 128.34 |
| case_03_conflict | 0.57 | 0.14 | 1.00 | 1.00 | 0.00 | 0.00 | 0.00 | 0.00 | 23.24 |
| **mean** | 0.75 | 0.67 | 1.00 | 0.89 | 0.00 | 0.00 | 0.00 | 0.00 | 78.57 |

Missed facts: case_01_simple: ['F7']; case_02_medium: none; case_03_conflict: ['F1', 'F2', 'F3', 'F4', 'F5', 'F7']
