# Your Turn baseline (before extensions)

Captured on 2026-10-13 with the deterministic input CSV files (seed 25), before changing Extensions 1 and 3.

## M2 — Inference levers

| Metric | Baseline result |
|---|---:|
| Requests | 2,400 |
| Tokens | 7,533,027 |
| Naive cost | $48.87/day |
| Naive $/1M-token | $6.488 |
| Optimized cost | $8.48/day |
| Optimized $/1M-token | $1.126 |
| Savings | 82.6% |

The old implementation applied cached-read pricing whenever `cached_input_tokens > 0`; it did not charge for creating the cache entry or test whether it had enough reuse.

## M3 — Purchasing

| Job | GPU | Old tier | On-demand/month | Old optimized/month |
|---|---|---|---:|---:|
| job-train-llm | H100 | spot | $12,000 | $7,596 |
| job-train-embed | A100 | spot | $2,148 | $1,393 |
| job-finetune | H100 | spot | $900 | $570 |
| job-infer-chat | A10G | reserved | $4,320 | $2,592 |
| job-infer-rag | A100 | reserved | $3,866 | $2,160 |
| job-infer-search | L4 | reserved | $1,728 | $972 |
| job-dev-sandbox | A10G | spot | $480 | $203 |
| job-batch-eval | H100 | spot | $225 | $142 |
| **Total** | | | **$25,667** | **$15,627** |

Old M3 savings: **39.1%**. The old implementation used one 5%/GPU-hour interruption assumption for every GPU and always priced reserved work at the 3-year rate. It also projected every job over 30 active days, ignoring the `days` column.
