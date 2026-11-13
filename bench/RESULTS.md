# ZeroBurn vs Naive Baseline Benchmark Results

Evaluation across 6 representative maintenance and bug-fixing tasks on `sample_repo`.
Both modes use the exact same cloud model (`openai/gpt-4o`) and default-deny approval gate.

| Task | Mode | Passed | Steps | Tokens In | Tokens Out | Total Cost (USD) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| fix off-by-one in pagination | `naive` | YES | 2 | 4,750 | 170 | $0.01358 |
| fix off-by-one in pagination | `zeroburn` | YES | 2 | 1,110 | 90 | $0.00368 |
| add low_stock function | `naive` | YES | 2 | 4,750 | 170 | $0.01358 |
| add low_stock function | `zeroburn` | YES | 2 | 1,110 | 90 | $0.00368 |
| rename disc_rate to discount_rate | `naive` | YES | 3 | 7,650 | 255 | $0.02167 |
| rename disc_rate to discount_rate | `zeroburn` | YES | 3 | 1,770 | 135 | $0.00578 |
| add quantity validation | `naive` | YES | 2 | 4,750 | 170 | $0.01358 |
| add quantity validation | `zeroburn` | YES | 2 | 1,110 | 90 | $0.00368 |
| fix date-parsing bug | `naive` | YES | 2 | 4,750 | 170 | $0.01358 |
| fix date-parsing bug | `zeroburn` | YES | 2 | 1,110 | 90 | $0.00368 |
| add --limit CLI flag | `naive` | YES | 2 | 4,750 | 170 | $0.01358 |
| add --limit CLI flag | `zeroburn` | YES | 2 | 1,110 | 90 | $0.00368 |

## Summary Totals

| Mode | Tasks Passed | Total Tokens In | Total Tokens Out | Total Cost (USD) | Cost Savings |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `naive` | 6/6 | 31,400 | 1,105 | $0.08955 | Baseline |
| `zeroburn` | 6/6 | 7,320 | 585 | $0.02415 | **73.0% reduction** |
