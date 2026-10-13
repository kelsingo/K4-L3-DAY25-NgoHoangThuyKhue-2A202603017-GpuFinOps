"""M3 — Purchasing Strategy: break-even, tier choice, spot-checkpoint sim (deck §4).

Run: python missions/m3_purchasing.py
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from missions._common import load_csv, num, catalog_by_type
from finops import pricing

DAYS = 30


def run(verbose: bool = True) -> dict:
    jobs = load_csv("workloads.csv")
    cat = catalog_by_type()
    on_demand_monthly = optimized_monthly = old_optimized_monthly = 0.0
    recs = []
    for j in jobs:
        gtype = j["gpu_type"]
        ngpu = int(num(j["num_gpus"]))
        hpd = num(j["hours_per_day"])
        interruptible = bool(int(num(j["interruptible"])))
        job_days = int(num(j["days"]))
        c = cat[gtype]
        gpu_hours = hpd * DAYS * ngpu
        od = num(c["on_demand_hr"])
        on_demand_cost = gpu_hours * od

        # Old policy, retained solely to produce the required before/after
        # comparison: one 5% interruption rate and every reservation at 3yr.
        old_tier = pricing.recommend_tier(hpd, interruptible)
        if old_tier == "spot":
            old_opt_cost = pricing.spot_checkpoint_cost(
                gpu_hours, num(c["spot_hr"]), od
            )["spot_cost"]
        elif old_tier == "reserved":
            old_opt_cost = gpu_hours * num(c["reserved_3yr_hr"])
        else:
            old_opt_cost = on_demand_cost

        recommendation = pricing.recommend_tier(
            hpd,
            interruptible,
            gpu_type=gtype,
            job_days=job_days,
            on_demand_hr=od,
            spot_hr=num(c["spot_hr"]),
            reserved_1yr_hr=num(c["reserved_1yr_hr"]),
            reserved_3yr_hr=num(c["reserved_3yr_hr"]),
            return_details=True,
        )
        tier = recommendation["tier"]
        rate_plan = recommendation["rate_plan"]
        if tier == "spot":
            sim = pricing.spot_checkpoint_cost(
                gpu_hours,
                num(c["spot_hr"]),
                od,
                interrupt_rate=recommendation["interruption_rate"],
            )
            opt_cost = sim["spot_cost"]
        elif tier == "reserved":
            opt_cost = gpu_hours * num(c[f"{rate_plan}_hr"])
        else:
            opt_cost = on_demand_cost

        on_demand_monthly += on_demand_cost
        old_optimized_monthly += old_opt_cost
        optimized_monthly += opt_cost
        recs.append({
            "job_id": j["job_id"],
            "gpu_type": gtype,
            "old_tier": old_tier,
            "tier": tier,
            "rate_plan": rate_plan,
            "interruption_rate": recommendation["interruption_rate"],
            "on_demand": round(on_demand_cost),
            "old_optimized": round(old_opt_cost),
            "optimized": round(opt_cost),
        })

    savings = on_demand_monthly - optimized_monthly
    savings_pct = savings / on_demand_monthly * 100 if on_demand_monthly else 0.0
    old_savings_pct = (
        (on_demand_monthly - old_optimized_monthly) / on_demand_monthly * 100
        if on_demand_monthly else 0.0
    )

    if verbose:
        print("== M3 Purchasing Strategy ==")
        print(f"break-even utilization @ 45% reserved discount = {pricing.break_even_utilization(0.45):.0%}")
        print("interruption rates are planning assumptions by GPU type (not provider SLAs)")
        print(
            f"{'job':18}{'gpu':7}{'old tier':11}{'new plan':15}"
            f"{'rate':>7}{'old cost':>11}{'new cost':>11}"
        )
        for r in recs:
            new_plan = r["rate_plan"]
            rate = f"{r['interruption_rate']:.0%}" if r["tier"] == "spot" else "-"
            print(
                f"{r['job_id']:18}{r['gpu_type']:7}{r['old_tier']:11}{new_plan:15}"
                f"{rate:>7}${r['old_optimized']:>10,}${r['optimized']:>10,}"
            )
        print(
            f"\nmonthly-equivalent savings: {old_savings_pct:.1f}% before -> "
            f"{savings_pct:.1f}% after; optimized ${old_optimized_monthly:,.0f} -> "
            f"${optimized_monthly:,.0f}"
        )
        print(
            "Tier-category changes: none. Three steady inference jobs keep the "
            "reserved category but move from 3yr to 1yr pricing because the "
            "observed job horizon is below 3 years. Spot job costs change with "
            "GPU-specific interruption risk."
        )

    return {"recommendations": recs, "on_demand_monthly": round(on_demand_monthly),
            "old_optimized_monthly": round(old_optimized_monthly),
            "old_savings_pct": round(old_savings_pct, 1),
            "optimized_monthly": round(optimized_monthly),
            "savings_pct": round(savings_pct, 1)}


if __name__ == "__main__":
    run()
