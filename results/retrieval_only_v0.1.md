## retrieval_only_v0.1 (extractive)

| case_id | retrieval_recall | fact_recall | citation_validity | citation_accuracy | unsupported_claims | conflict_recall_text | conflict_recall | verdict_accuracy | latency_s |
|---|---|---|---|---|---|---|---|---|---|
| case_01_simple | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | – | – | – | 0.12 |
| case_02_medium | 0.67 | 0.50 | 1.00 | 0.67 | 0.00 | – | – | – | 0.18 |
| case_03_conflict | 0.57 | 0.14 | 1.00 | 1.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.10 |
| **mean** | 0.75 | 0.55 | 1.00 | 0.89 | 0.00 | 0.00 | 0.00 | 0.00 | 0.14 |

Missed facts: case_01_simple: none; case_02_medium: ['F3', 'F4', 'F5']; case_03_conflict: ['F1', 'F2', 'F3', 'F4', 'F5', 'F7']
