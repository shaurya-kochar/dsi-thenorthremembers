## retrieval_only_v0.1 (extractive)

| Case | Retr. recall | Fact recall | Cit. validity | Cit. accuracy | Unsupported | Conflict (text) | Conflict (struct.) | Verdict | Latency (s) |
|---|---|---|---|---|---|---|---|---|---|
| case_01_simple | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | – | – | – | 0.21 |
| case_02_medium | 0.67 | 0.50 | 1.00 | 0.67 | 0.00 | – | – | – | 0.24 |
| case_03_conflict | 0.57 | 0.14 | 1.00 | 1.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.14 |
| **mean** | 0.75 | 0.55 | 1.00 | 0.89 | 0.00 | 0.00 | 0.00 | 0.00 | 0.20 |

Missed facts: case_01_simple: none; case_02_medium: ['F3', 'F4', 'F5']; case_03_conflict: ['F1', 'F2', 'F3', 'F4', 'F5', 'F7']
