# NimbusAI — GPU Cost Optimization Report

**Period:** monthly  
**Baseline spend:** $27,133  
**Optimized spend:** $14,751  
**Projected savings:** $12,382  (**46%**)

## Savings by lever

| Lever | Savings (USD) |
|---|---|
| Inference (cascade/cache/batch) | $1,195 |
| Purchasing (spot/reserved) | $8,055 |
| Right-size util-lies | $2,532 |
| Kill idle GPUs | $600 |

## Sustainability

- Energy per query: 0.24 Wh
- Carbon per query: 0.091 gCO2e
- Cheapest+cleanest region: europe-north1

_Figures are June-2026 as-of snapshots; re-baseline before acting._

## Your Turn extensions — before/after

The deterministic pre-change output is archived in `outputs/your_turn_baseline.md`.

### Extension 1 — risk- and duration-aware purchasing

| Job | GPU | Old tier | New plan | Interruption assumption | Cost before | Cost after |
|---|---|---|---|---:|---:|---:|
| job-train-llm | H100 | spot | spot | 3% | $7,596 | $7,524 |
| job-train-embed | A100 | spot | spot | 6% | $1,393 | $1,399 |
| job-finetune | H100 | spot | spot | 3% | $570 | $564 |
| job-infer-chat | A10G | reserved | reserved_1yr | n/a | $2,592 | $3,456 |
| job-infer-rag | A100 | reserved | reserved_1yr | n/a | $2,160 | $3,024 |
| job-infer-search | L4 | reserved | reserved_1yr | n/a | $972 | $1,296 |
| job-dev-sandbox | A10G | spot | spot | 10% | $203 | $207 |
| job-batch-eval | H100 | spot | spot | 3% | $142 | $141 |

M3 savings changes from **39.1%** to **31.4%**. No job changes the broad tier category. The three steady inference jobs change from an unjustified 3-year rate to the 1-year rate because their observed horizon is under three years. Spot costs move slightly because H100/A100/A10G use 3%/6%/10% assumed hourly interruption rates instead of one 5% value. These are explicit planning assumptions, not provider SLAs; re-baseline before purchase.

### Extension 2 — MBU-aware right-sizing

| GPU | Current → proposed | Required / proposed VRAM | Observed / proposed peak BW (TB/s) | $/GB-VRAM before → after | Reason | Potential USD/month |
|---|---|---:|---:|---:|---|---:|
| gpu-h100-0 | H100 → MI300X | 80 / 192 GB | 1.50 / 5.30 | $0.0312 → $0.0102 | meets VRAM + observed bandwidth at lower $/GB and $/hour | $396 |
| gpu-h100-1 | H100 → MI300X | 80 / 192 GB | 1.47 / 5.30 | $0.0312 → $0.0102 | meets VRAM + observed bandwidth at lower $/GB and $/hour | $396 |
| gpu-h100-2 | H100 → MI300X | 80 / 192 GB | 1.42 / 5.30 | $0.0312 → $0.0102 | meets VRAM + observed bandwidth at lower $/GB and $/hour | $396 |
| gpu-h100-3 | H100 → MI300X | 80 / 192 GB | 1.49 / 5.30 | $0.0312 → $0.0102 | meets VRAM + observed bandwidth at lower $/GB and $/hour | $396 |
| gpu-h100-4 | H100 → MI300X | 80 / 192 GB | 0.69 / 5.30 | $0.0312 → $0.0102 | meets VRAM + observed bandwidth at lower $/GB and $/hour | $396 |
| gpu-h100-5 | H100 → MI300X | 80 / 192 GB | 0.91 / 5.30 | $0.0312 → $0.0102 | meets VRAM + observed bandwidth at lower $/GB and $/hour | $264 |
| gpu-a10g-0 | A10G → L4 | 24 / 24 GB | 0.14 / 0.30 | $0.0417 → $0.0333 | meets VRAM + observed bandwidth at lower $/GB and $/hour | $144 |
| gpu-a10g-1 | A10G → L4 | 24 / 24 GB | 0.18 / 0.30 | $0.0417 → $0.0333 | meets VRAM + observed bandwidth at lower $/GB and $/hour | $144 |

Potential right-sizing savings are **$2,532/month**. The selector does not merely choose the cheapest GPU-hour: it requires at least the current GPU's full HBM capacity, enough peak bandwidth for the observed bandwidth, a lower $/GB-VRAM, and a lower hourly price. This is a feasibility screen only—there is no benchmark proving unchanged throughput or latency, so canary benchmarks are required before rollout.

### Extension 3 — cache write economics

Assumption: one cache write costs 1.25× the normal input-token price. Because the CSV has no prefix ID/read count, average reads are assumed to be 1 for small-tier prefixes and 4 for large-tier prefixes.

| Tier | Avg reads | Break-even reads | Cache enabled |
|---|---:|---:|---|
| small | 1.0 | 1.39 | False |
| large | 4.0 | 1.39 | True |

| Cache policy | Daily cost | $/1M-token |
|---|---:|---:|
| Old calculation (write cost omitted) | $8.48 | $1.126 |
| New mixed-reuse policy (write included) | $9.05 | $1.202 |
| Low reuse: 1 read/prefix | $9.66 | $1.282 |
| High reuse: 8 reads/prefix | $8.69 | $1.154 |

The break-even is 1.39 reads, so one-read prefixes stay uncached while four- or eight-read prefixes repay the write. Including cache creation raises the realistic optimized result from the old $1.126 to **$1.202/1M-token**; total M2 savings remains **81.5%**.