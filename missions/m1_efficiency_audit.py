"""M1 — Efficiency Audit: MFU/MBU, the GPU-Util lie, and idle waste (deck §5).

Run: python missions/m1_efficiency_audit.py
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from collections import defaultdict
from missions._common import load_csv, num, catalog_by_type
from finops import metrics


def run(verbose: bool = True) -> dict:
    tel = load_csv("gpu_telemetry.csv")
    cat = catalog_by_type()

    # per-row MFU/MBU, then aggregate per GPU
    agg = defaultdict(lambda: {
        "util": [], "mfu": [], "mbu": [], "bw": [], "type": None,
        "idle_hours": 0,
    })
    for r in tel:
        gtype = r["gpu_type"]
        peak_fp16 = num(cat[gtype]["peak_tflops_fp16"])
        peak_bw = num(cat[gtype]["peak_bw_tbs"])
        mfu = metrics.compute_mfu(num(r["achieved_tflops"]), peak_fp16)
        mbu = metrics.compute_mbu(num(r["achieved_bw_tbs"]), peak_bw)
        a = agg[r["gpu_id"]]
        a["type"] = gtype
        a["util"].append(num(r["gpu_util_pct"]))
        a["mfu"].append(mfu)
        a["mbu"].append(mbu)
        a["bw"].append(num(r["achieved_bw_tbs"]))
        if num(r["gpu_util_pct"]) < 10:  # effectively idle this interval (1h)
            a["idle_hours"] += 1

    summary = []
    for gid, a in agg.items():
        summary.append({
            "gpu_id": gid, "gpu_type": a["type"],
            "gpu_util_pct": round(sum(a["util"]) / len(a["util"]), 1),
            "mfu": round(sum(a["mfu"]) / len(a["mfu"]), 3),
            "mbu": round(sum(a["mbu"]) / len(a["mbu"]), 3),
            "achieved_bw_tbs": round(sum(a["bw"]) / len(a["bw"]), 3),
            "idle_hours": a["idle_hours"],
        })

    lies = metrics.flag_util_lies(summary)
    idle_waste = 0.0
    for s in summary:
        on_demand = num(catalog_by_type()[s["gpu_type"]]["on_demand_hr"])
        idle_waste += metrics.idle_waste_usd(s["idle_hours"], on_demand)

    # Extension 2: conservative MBU-aware right-sizing. We lack measured memory
    # occupancy, so required VRAM is conservatively set to the current GPU's
    # full HBM. A candidate must also sustain the observed bandwidth, cost less
    # per hour, and have a better $/GB-VRAM ratio. MBU > MFU is used only as a
    # proxy for memory pressure; a benchmark is still required before migration.
    rightsizing = []
    for s in summary:
        if s["mbu"] <= s["mfu"]:
            continue
        current = cat[s["gpu_type"]]
        required_hbm = num(current["hbm_gb"])
        current_hr = num(current["on_demand_hr"])
        current_per_gb = current_hr / required_hbm
        candidates = []
        for candidate_type, candidate in cat.items():
            candidate_hbm = num(candidate["hbm_gb"])
            candidate_hr = num(candidate["on_demand_hr"])
            candidate_bw = num(candidate["peak_bw_tbs"])
            candidate_per_gb = candidate_hr / candidate_hbm
            if (
                candidate_type != s["gpu_type"]
                and candidate_hbm >= required_hbm
                and candidate_bw >= s["achieved_bw_tbs"]
                and candidate_hr < current_hr
                and candidate_per_gb < current_per_gb
            ):
                candidates.append((candidate_per_gb, candidate_hr, candidate_type, candidate))
        if not candidates:
            continue
        _, target_hr, target_type, target = min(candidates)
        active_hours_month = (24 - s["idle_hours"]) * 30
        savings_monthly = (current_hr - target_hr) * active_hours_month
        rightsizing.append({
            "gpu_id": s["gpu_id"],
            "current_gpu": s["gpu_type"],
            "recommended_gpu": target_type,
            "required_hbm_gb": required_hbm,
            "target_hbm_gb": num(target["hbm_gb"]),
            "observed_bw_tbs": s["achieved_bw_tbs"],
            "target_peak_bw_tbs": num(target["peak_bw_tbs"]),
            "current_cost_per_gb": current_per_gb,
            "target_cost_per_gb": target_hr / num(target["hbm_gb"]),
            "monthly_savings": round(savings_monthly, 2),
            "reason": "meets VRAM + observed bandwidth at lower $/GB and $/hour",
        })

    if verbose:
        print("== M1 Efficiency Audit ==")
        print(f"{'GPU':14}{'type':7}{'util%':>7}{'MFU':>7}{'MBU':>7}{'idle_h':>8}")
        for s in sorted(summary, key=lambda x: x["mfu"]):
            print(f"{s['gpu_id']:14}{s['gpu_type']:7}{s['gpu_util_pct']:>7}{s['mfu']:>7}{s['mbu']:>7}{s['idle_hours']:>8}")
        print(f"\nGPU-Util LIES (util>=90% but MFU<30%): {[l['gpu_id'] for l in lies]}")
        print(f"Idle waste (1 day): ${idle_waste:,.2f}  ->  ${idle_waste*30:,.0f}/month")
        print("\nMBU-aware right-sizing (benchmark required before rollout):")
        print(f"{'GPU':14}{'current -> target':20}{'VRAM need/have':>17}{'BW obs/peak':>15}{'save/mo':>11}")
        for r in rightsizing:
            pair = f"{r['current_gpu']} -> {r['recommended_gpu']}"
            memory = f"{r['required_hbm_gb']:.0f}/{r['target_hbm_gb']:.0f} GB"
            bandwidth = f"{r['observed_bw_tbs']:.2f}/{r['target_peak_bw_tbs']:.2f}"
            print(
                f"{r['gpu_id']:14}{pair:20}{memory:>17}{bandwidth:>15}"
                f"${r['monthly_savings']:>10,.0f}"
            )
        print(
            "Limit: peak bandwidth is a feasibility screen, not proof that model "
            "throughput/latency will be unchanged; validate with a workload benchmark."
        )

    return {
        "summary": summary,
        "lies": lies,
        "idle_waste_daily": round(idle_waste, 2),
        "rightsizing": rightsizing,
        "rightsizing_monthly_savings": round(
            sum(r["monthly_savings"] for r in rightsizing), 2
        ),
    }


if __name__ == "__main__":
    run()
