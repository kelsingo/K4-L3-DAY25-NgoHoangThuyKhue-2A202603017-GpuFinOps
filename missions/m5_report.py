"""M5 — Optimization Report: combine M1-M4 into baseline-vs-optimized (deck §1/§11).

Run: python missions/m5_report.py   ->  outputs/report.md + outputs/savings.png
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import os
from missions._common import ROOT
from finops import report, sustainability
from missions import m1_efficiency_audit, m2_inference_levers, m3_purchasing

DAYS = 30
def run(verbose: bool = True) -> dict:
    r1 = m1_efficiency_audit.run(verbose=False)
    r2 = m2_inference_levers.run(verbose=False)
    r3 = m3_purchasing.run(verbose=False)

    # --- buckets ---
    infer_savings = (r2["baseline_daily"] - r2["optimized_daily"]) * DAYS
    purchasing_savings = r3["on_demand_monthly"] - r3["optimized_monthly"]

    idle_savings = r1["idle_waste_daily"] * DAYS
    rightsize_savings = r1["rightsizing_monthly_savings"]

    levers = {
        "Inference (cascade/cache/batch)": round(infer_savings),
        "Purchasing (spot/reserved)": round(purchasing_savings),
        "Right-size util-lies": round(rightsize_savings),
        "Kill idle GPUs": round(idle_savings),
    }
    baseline = r2["baseline_daily"] * DAYS + r3["on_demand_monthly"]
    optimized = baseline - sum(levers.values())
    total_pct = sum(levers.values()) / baseline * 100 if baseline else 0.0

    # --- sustainability snapshot ---
    median_tokens = 800
    wh = sustainability.wh_per_query(median_tokens)
    sust = {
        "wh_per_query": wh,
        "carbon_g": sustainability.carbon_g(wh, "us-east-1"),
        "best_region": min(sustainability.REGION_CARBON, key=sustainability.REGION_CARBON.get),
    }

    md = report.build_report(baseline, optimized, levers, sustainability=sust)

    # Persist the measured Your Turn results in the generated deliverable so a
    # later M5 run cannot overwrite the extension write-up.
    extension_lines = [
        "",
        "## Your Turn extensions — before/after",
        "",
        "The deterministic pre-change output is archived in `outputs/your_turn_baseline.md`.",
        "",
        "### Extension 1 — risk- and duration-aware purchasing",
        "",
        "| Job | GPU | Old tier | New plan | Interruption assumption | Cost before | Cost after |",
        "|---|---|---|---|---:|---:|---:|",
    ]
    for rec in r3["recommendations"]:
        rate = f"{rec['interruption_rate']:.0%}" if rec["tier"] == "spot" else "n/a"
        extension_lines.append(
            f"| {rec['job_id']} | {rec['gpu_type']} | {rec['old_tier']} | "
            f"{rec['rate_plan']} | {rate} | ${rec['old_optimized']:,.0f} | "
            f"${rec['optimized']:,.0f} |"
        )
    extension_lines += [
        "",
        f"M3 savings changes from **{r3['old_savings_pct']:.1f}%** to "
        f"**{r3['savings_pct']:.1f}%**. No job changes the broad tier category. "
        "The three steady inference jobs change from an unjustified 3-year rate "
        "to the 1-year rate because their observed horizon is under three years. "
        "Spot costs move slightly because H100/A100/A10G use 3%/6%/10% assumed "
        "hourly interruption rates instead of one 5% value. These are explicit "
        "planning assumptions, not provider SLAs; re-baseline before purchase.",
        "",
        "### Extension 2 — MBU-aware right-sizing",
        "",
        "| GPU | Current → proposed | Required / proposed VRAM | Observed / proposed peak BW (TB/s) | $/GB-VRAM before → after | Reason | Potential USD/month |",
        "|---|---|---:|---:|---:|---|---:|",
    ]
    for rec in r1["rightsizing"]:
        extension_lines.append(
            f"| {rec['gpu_id']} | {rec['current_gpu']} → {rec['recommended_gpu']} | "
            f"{rec['required_hbm_gb']:.0f} / {rec['target_hbm_gb']:.0f} GB | "
            f"{rec['observed_bw_tbs']:.2f} / {rec['target_peak_bw_tbs']:.2f} | "
            f"${rec['current_cost_per_gb']:.4f} → ${rec['target_cost_per_gb']:.4f} | "
            f"{rec['reason']} | "
            f"${rec['monthly_savings']:,.0f} |"
        )
    extension_lines += [
        "",
        f"Potential right-sizing savings are **${r1['rightsizing_monthly_savings']:,.0f}/month**. "
        "The selector does not merely choose the cheapest GPU-hour: it requires "
        "at least the current GPU's full HBM capacity, enough peak bandwidth for "
        "the observed bandwidth, a lower $/GB-VRAM, and a lower hourly price. "
        "This is a feasibility screen only—there is no benchmark proving unchanged "
        "throughput or latency, so canary benchmarks are required before rollout.",
        "",
        "### Extension 3 — cache write economics",
        "",
        "Assumption: one cache write costs 1.25× the normal input-token price. "
        "Because the CSV has no prefix ID/read count, average reads are assumed "
        "to be 1 for small-tier prefixes and 4 for large-tier prefixes.",
        "",
        "| Tier | Avg reads | Break-even reads | Cache enabled |",
        "|---|---:|---:|---|",
    ]
    for tier, decision in r2["cache_decisions"].items():
        extension_lines.append(
            f"| {tier} | {decision['avg_reads']:.1f} | "
            f"{decision['break_even_reads']:.2f} | {decision['enabled']} |"
        )
    scenarios = r2["cache_scenarios"]
    extension_lines += [
        "",
        "| Cache policy | Daily cost | $/1M-token |",
        "|---|---:|---:|",
        f"| Old calculation (write cost omitted) | ${r2['legacy_optimized_daily']:.2f} | ${r2['legacy_optimized_per_m']:.3f} |",
        f"| New mixed-reuse policy (write included) | ${r2['optimized_daily']:.2f} | ${r2['optimized_per_m']:.3f} |",
        f"| Low reuse: 1 read/prefix | ${scenarios['low_reads_daily']:.2f} | ${scenarios['low_reads_per_m']:.3f} |",
        f"| High reuse: 8 reads/prefix | ${scenarios['high_reads_daily']:.2f} | ${scenarios['high_reads_per_m']:.3f} |",
        "",
        "The break-even is 1.39 reads, so one-read prefixes stay uncached while "
        "four- or eight-read prefixes repay the write. Including cache creation "
        "raises the realistic optimized result from the old $1.126 to "
        f"**${r2['optimized_per_m']:.3f}/1M-token**; total M2 savings remains "
        f"**{r2['savings_pct']:.1f}%**.",
    ]
    md += "\n" + "\n".join(extension_lines)
    out_md = os.path.join(ROOT, "outputs", "report.md")
    os.makedirs(os.path.dirname(out_md), exist_ok=True)
    with open(out_md, "w") as f:
        f.write(md)
    png = report.savings_waterfall(levers, os.path.join(ROOT, "outputs", "savings.png"))

    if verbose:
        print("== M5 Optimization Report ==")
        print(md)
        print(f"\nWritten: outputs/report.md" + (f" + outputs/savings.png" if png else " (matplotlib absent: PNG skipped)"))

    return {"baseline_monthly": round(baseline), "optimized_monthly": round(optimized),
            "levers": levers, "total_savings_pct": round(total_pct, 1)}


if __name__ == "__main__":
    run()
